// qengine.cpp -- thin command-line bridge to libquackle.
//
// Reads simple "key=value" commands on stdin and writes line-based results on
// stdout.  The game (Python) owns all rules; this process only answers
// "what are the best plays for this position?" using Quackle's generator,
// evaluator and simulation players.
//
// Protocol
//   INIT data=<dir> dawg=<file> lexicon=<name>
//   MOVES board=<225 chars> rack=<letters> bag=<letters> my=<score> opp=<score>
//         level=<1..5> top=<n> secs=<n>
//   STATIC <same fields>          (static evaluation only)
//   PING / QUIT
//
// board uses '.' for an empty square, upper case for a plain tile and lower
// case for a blank.

#include <algorithm>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "alphabetparameters.h"
#include "bag.h"
#include "board.h"
#include "boardparameters.h"
#include "computerplayer.h"
#include "datamanager.h"
#include "game.h"
#include "lexiconparameters.h"
#include "player.h"
#include "playerlist.h"
#include "rack.h"
#include "resolvent.h"
#include "strategyparameters.h"
#include "trademarkedboards.h"

using namespace Quackle;

namespace
{

Quackle::DataManager *g_data = nullptr;

// libquackle chats to std::cout/std::cerr while it thinks.  Keep that away from
// the protocol stream.
class NullBuffer : public std::streambuf
{
protected:
	int overflow(int c) override { return c; }
};

NullBuffer g_null;
std::streambuf *g_outBuffer = nullptr;
std::streambuf *g_errBuffer = nullptr;

void muteLibraryOutput()
{
	if (!g_outBuffer)
	{
		g_outBuffer = std::cout.rdbuf();
		g_errBuffer = std::cerr.rdbuf();
	}
	std::cout.rdbuf(&g_null);
	std::cerr.rdbuf(&g_null);
}

void unmuteLibraryOutput()
{
	if (g_outBuffer)
	{
		std::cout.rdbuf(g_outBuffer);
		std::cerr.rdbuf(g_errBuffer);
	}
}

// Board's tile array is protected and libquackle has no public setter for an
// arbitrary position, so build one with a small subclass.
class BuildableBoard : public Quackle::Board
{
public:
	void clearAll() { prepareEmptyBoard(); }

	void put(int row, int col, Letter letter, bool blank)
	{
		if (letter == QUACKLE_NULL_MARK)
			return;
		m_letters[row][col] = blank ? QUACKLE_ALPHABET_PARAMETERS->setBlankness(letter) : letter;
		m_isBlank[row][col] = blank;
		m_isBritish[row][col] = false;
		m_empty = false;
	}
};

std::map<std::string, std::string> parseFields(const std::string &line)
{
	std::map<std::string, std::string> fields;
	std::istringstream stream(line);
	std::string token;
	while (stream >> token)
	{
		std::string::size_type pos = token.find('=');
		if (pos == std::string::npos)
			continue;
		fields[token.substr(0, pos)] = token.substr(pos + 1);
	}
	return fields;
}

std::string field(const std::map<std::string, std::string> &fields, const std::string &key, const std::string &fallback = "")
{
	std::map<std::string, std::string>::const_iterator it = fields.find(key);
	return it == fields.end() ? fallback : it->second;
}

int intField(const std::map<std::string, std::string> &fields, const std::string &key, int fallback)
{
	const std::string value = field(fields, key);
	return value.empty() ? fallback : std::atoi(value.c_str());
}

Quackle::LetterString encodeLetters(const std::string &text)
{
	UVString leftover;
	LetterString encoded = QUACKLE_ALPHABET_PARAMETERS->encode(UVString(text), &leftover);
	return encoded;
}

// Bags are longer than a LetterString (40 chars), so build them tile by tile.
Quackle::Bag makeBag(const std::string &text)
{
	LongLetterString tiles;
	for (size_t i = 0; i < text.size(); ++i)
	{
		LetterString encoded = encodeLetters(std::string(1, text[i]));
		for (unsigned int j = 0; j < encoded.length(); ++j)
			tiles.push_back(encoded[j]);
	}
	Quackle::Bag bag;
	bag.clear();
	bag.toss(tiles);
	return bag;
}

Quackle::ComputerPlayer *makePlayer(int level)
{
	if (level >= 5)
		return new TorontoPlayer;
	if (level == 4)
		return new FiveMinutePlayer;
	if (level == 3)
		return new TwentySecondPlayer;
	return new StaticPlayer;
}

bool loadEngine(const std::string &dataDir, const std::string &dawgPath, const std::string &lexicon)
{
	if (!g_data)
		g_data = new Quackle::DataManager;

	QUACKLE_DATAMANAGER->setAppDataDirectory(dataDir);
	QUACKLE_DATAMANAGER->setBackupLexicon("default_english");
	QUACKLE_DATAMANAGER->lexiconParameters()->loadDawg(dawgPath);
	if (!QUACKLE_DATAMANAGER->lexiconParameters()->hasDawg())
		return false;

	QUACKLE_DATAMANAGER->strategyParameters()->initialize(lexicon);
	QUACKLE_DATAMANAGER->setBoardParameters(new ScrabbleBoard());
	QUACKLE_DATAMANAGER->setAlphabetParameters(new Quackle::EnglishAlphabetParameters);
	return true;
}

void fillBoard(BuildableBoard &board, const std::string &grid)
{
	board.clearAll();
	for (size_t i = 0; i < grid.size() && i < 225; ++i)
	{
		char c = grid[i];
		if (c == '.' || c == '-' || c == ' ')
			continue;
		const bool blank = (c >= 'a' && c <= 'z');
		const char upper = blank ? static_cast<char>(c - 'a' + 'A') : c;
		LetterString letter = encodeLetters(std::string(1, upper));
		if (letter.length() == 0)
			continue;
		board.put(static_cast<int>(i / 15), static_cast<int>(i % 15), letter[0], blank);
	}
}

// Build a move's tiles from a pattern like ".ARTIEST" (dot = already on the
// board, lowercase = blank).
Quackle::LetterString encodePattern(const std::string &pattern)
{
	Quackle::LetterString tiles;
	for (size_t i = 0; i < pattern.size(); ++i)
	{
		const char c = pattern[i];
		if (c == '.')
			tiles += QUACKLE_PLAYED_THRU_MARK;
		else if (c == '?')
			tiles += QUACKLE_BLANK_MARK;
		else if (c >= 'a' && c <= 'z')
		{
			LetterString encoded = encodeLetters(std::string(1, static_cast<char>(c - 'a' + 'A')));
			if (encoded.length() > 0)
				tiles += QUACKLE_ALPHABET_PARAMETERS->setBlankness(encoded[0]);
		}
		else
		{
			LetterString encoded = encodeLetters(std::string(1, c));
			if (encoded.length() > 0)
				tiles += encoded[0];
		}
	}
	return tiles;
}

std::string prettyTiles(const Move &move)
{
	if (move.action != Move::Place)
		return "";
	return QUACKLE_ALPHABET_PARAMETERS->userVisible(move.tiles());
}

std::string cleanWord(const Move &move)
{
	if (move.action != Move::Place)
		return "";
	const LetterString word = QUACKLE_ALPHABET_PARAMETERS->clearBlankness(move.wordTiles());
	return QUACKLE_ALPHABET_PARAMETERS->userVisible(word);
}

void printMove(const Move &move)
{
	const char *action = "play";
	if (move.action == Move::Exchange)
		action = "exchange";
	else if (move.action == Move::Pass)
		action = "pass";

	std::cout << "MOVE action=" << action
			  << " row=" << move.startrow
			  << " col=" << move.startcol
			  << " horiz=" << (move.horizontal ? 1 : 0)
			  << " score=" << move.score
			  << " equity=" << std::fixed << std::setprecision(2) << move.equity
			  << " win=" << std::setprecision(3) << move.win
			  << " word=" << cleanWord(move)
			  << " tiles=" << prettyTiles(move)
			  << " bingo=" << (move.isBingo ? 1 : 0)
			  << std::endl;
}

struct Request
{
	std::string rackText;
	std::string bagText;
	std::string grid;
	int level = 1;
	int top = 10;
	int myScore = 0;
	int oppScore = 0;
	double seconds = 2.0;
};

Request readRequest(const std::map<std::string, std::string> &fields)
{
	Request request;
	request.rackText = field(fields, "rack");
	request.bagText = field(fields, "bag");
	request.grid = field(fields, "board");
	request.level = intField(fields, "level", 1);
	request.top = intField(fields, "top", 10);
	request.myScore = intField(fields, "my", 0);
	request.oppScore = intField(fields, "opp", 0);
	request.seconds = std::atof(field(fields, "secs", "2").c_str());
	return request;
}

void buildPosition(const Request &request, Quackle::Game &game)
{
	Quackle::PlayerList players;

	Quackle::Player bot("Engine", Player::ComputerPlayerType, 0);
	bot.setAbbreviatedName("E");
	bot.setScore(request.myScore);
	players.push_back(bot);

	Quackle::Player opp("Opponent", Player::HumanPlayerType, 1);
	opp.setAbbreviatedName("O");
	opp.setScore(request.oppScore);
	players.push_back(opp);

	game.setPlayers(players);
	game.addPosition();
}

void configurePosition(Quackle::Game &game, const Request &request)
{
	GamePosition &pos = game.currentPosition();

	BuildableBoard board;
	fillBoard(board, request.grid);
	pos.setBoard(board);
	pos.ensureBoardIsPreparedForAnalysis();

	if (!pos.setCurrentPlayer(0))
		return;
	pos.setPlayerOnTurn(0);
	pos.setPlayerRack(0, Rack(encodeLetters(request.rackText)), false);
	pos.setBag(makeBag(request.bagText));
}

void emitMoves(const MoveList &moves, int limit)
{
	int printed = 0;
	for (MoveList::const_iterator it = moves.begin(); it != moves.end() && printed < limit; ++it)
	{
		if (it->action != Move::Place)
			continue;
		printMove(*it);
		++printed;
	}
	std::cout << "END n=" << printed << std::endl;
}

void handleMoves(const std::map<std::string, std::string> &fields)
{
	if (!g_data || !QUACKLE_LEXICON_PARAMETERS->hasDawg())
	{
		std::cout << "ERR no-lexicon" << std::endl;
		return;
	}

	Request request = readRequest(fields);
	Game game;
	buildPosition(request, game);
	configurePosition(game, request);

	std::unique_ptr<ComputerPlayer> player(makePlayer(request.level));
	ComputerParameters params;
	params.secondsPerTurn = std::max(1, static_cast<int>(request.seconds));
	params.inferring = false;
	player->setParameters(params);
	player->setPosition(game.currentPosition());

	MoveList moves;
	{
		muteLibraryOutput();
		moves = player->moves(std::max(1, request.top));
		unmuteLibraryOutput();
	}

	emitMoves(moves, std::max(1, request.top));
}

void handleEval(const std::map<std::string, std::string> &fields)
{
	if (!g_data || !QUACKLE_LEXICON_PARAMETERS->hasDawg())
	{
		std::cout << "ERR no-lexicon" << std::endl;
		return;
	}

	Request request = readRequest(fields);
	Game game;
	buildPosition(request, game);
	configurePosition(game, request);
	GamePosition &pos = game.currentPosition();

	const int row = intField(fields, "row", 0);
	const int col = intField(fields, "col", 0);
	const bool horizontal = intField(fields, "horiz", 0) != 0;
	const std::string pattern = field(fields, "tiles");

	Move move = Move::createPlaceMove(row, col, horizontal, encodePattern(pattern));
	{
		muteLibraryOutput();
		pos.scoreMove(move);
		unmuteLibraryOutput();
	}

	std::cout << "SCORE score=" << move.score
			  << " equity=" << std::fixed << std::setprecision(2) << move.equity
			  << " word=" << cleanWord(move)
			  << std::endl;
}

void handleStatic(const std::map<std::string, std::string> &fields)
{
	if (!g_data || !QUACKLE_LEXICON_PARAMETERS->hasDawg())
	{
		std::cout << "ERR no-lexicon" << std::endl;
		return;
	}

	Request request = readRequest(fields);
	Game game;
	buildPosition(request, game);
	configurePosition(game, request);
	GamePosition &pos = game.currentPosition();

	{
		muteLibraryOutput();
		pos.kibitz(std::max(1, request.top));
		unmuteLibraryOutput();
	}

	emitMoves(pos.moves(), std::max(1, request.top));
}

} // namespace

int main()
{
	std::ios::sync_with_stdio(false);
	std::string line;
	while (std::getline(std::cin, line))
	{
		if (line.empty())
			continue;

		std::istringstream parts(line);
		std::string command;
		parts >> command;

		std::map<std::string, std::string> fields = parseFields(line);

		if (command == "INIT")
		{
			const std::string dataDir = field(fields, "data");
			const std::string dawg = field(fields, "dawg");
			const std::string lexicon = field(fields, "lexicon", "csw");
			const bool ok = loadEngine(dataDir, dawg, lexicon);
			std::cout << (ok ? "OK engine=quackle-1.1.0" : "ERR dawg-load-failed") << std::endl;
		}
		else if (command == "MOVES")
		{
			handleMoves(fields);
		}
		else if (command == "STATIC")
		{
			handleStatic(fields);
		}
		else if (command == "EVAL")
		{
			handleEval(fields);
		}
		else if (command == "PING")
		{
			std::cout << "PONG" << std::endl;
		}
		else if (command == "QUIT")
		{
			std::cout << "BYE" << std::endl;
			break;
		}
		else
		{
			std::cout << "ERR unknown-command" << std::endl;
		}
		std::cout.flush();
	}

	return 0;
}
