from enum import IntEnum
import random

import unittest


class Card(IntEnum):
    princess = 8
    countess = 7
    king = 6
    prince = 5
    handmaid = 4
    baron = 3
    priest = 2
    guard = 1

default_deck = [Card.princess, Card.countess, Card.king, Card.prince,
                Card.handmaid, Card.handmaid, Card.baron, Card.baron,
                Card.priest, Card.priest,
                Card.guard, Card.guard, Card.guard, Card.guard, Card.guard]

def create_random_deck():
    return random.sample(default_deck, len(default_deck) - 1)

class Game(object):
    def __init__(self, players, deck=None):
        self.deck = deck if deck is not None else create_random_deck()
        self.players = players
        self.hands = {x: self.deck.pop(0) for x in self.players}
        self.draw_card()

    def draw_card(self):
        player = self.players.pop(0)
        card = self.hands[player]
        new_card = self.deck.pop(0)
        self.on_turn = player, card, new_card

    def play_turn(self, who, card, nominated_player=None, nominated_card=None):
        player, card_one, card_two = self.on_turn
        if player != who:
            raise Exception("It's not your turn: " + player + " " + str(self.players))
        if card not in [card_one, card_two]:
            raise Exception("Illegal attempt to play a card you do not have.")
        kept_card = card_two if card == card_one else card_one

        if card == Card.guard:
            if nominated_player is None:
                raise Exception("You have to nominate a player to play the guard")
            if nominated_card is None:
                raise Exception("You have to nominate a card to play the guard")
            if nominated_card == Card.guard:
                raise Exception("You cannot guard a guard")
            nominated_players_card = self.hands[nominated_player]
            if nominated_card == nominated_players_card:
                # Nominated player is out of the game
                self.players.remove(nominated_player)

        if card == Card.baron:
            if nominated_player is None:
                raise Exception("You have to nominate a player to play the baron.")
            if nominated_player not in self.players:
                raise Exception("You have to baron against a player still in the game.")
            opponents_card = self.hands[nominated_player]
            if kept_card > opponents_card:
                self.players.remove(nominated_player)
            elif opponents_card > kept_card:
                # Do nothing, but the current player is out of the game so we
                # return without placing the current player 
                return
            # If the cards are equal nothing happens.

        if card == Card.countess:
            # This is fine, we need to check above that a player never manages
            # to avoid discarding the countess when they hold the prince or the
            # king, but discarding the countess is always fine, but has no
            # effect.
            pass

        if card == Card.princess:
            # The player is out, so do not append them to the back of the
            # players list.
            return

        self.hands[player] = kept_card
        self.players.append(player)

class GameTest(unittest.TestCase):
    def test_guard_wins(self):
        """ In this test we check that a player with a guard can knock out
            the other players. This will be more or less the shortest game
            possible in which player 1 knocks out player 2, player 3 knocks
            out player 4 and then player 1 again knocks out player 2.
        """
        # We set the deck so that we know what comes next.
        deck = [Card.guard, # Player 1's dealt card.
                Card.priest, # Player 2's dealt card, which p1 will guess.
                Card.guard, # Player 3's dealt card.
                Card.priest, # Player 4's dealt card which p3 will guess.
                Card.guard, # Player 1's drawn card.
                Card.baron, # Player 3's drawn card which p1 will guess and win.
                Card.baron # Player 1 still needs to draw a card.
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a', Card.guard, nominated_player='b', nominated_card=Card.priest)
        game.draw_card()
        game.play_turn('c', Card.guard, nominated_player='d', nominated_card=Card.priest)
        game.draw_card()
        game.play_turn('a', Card.guard, nominated_player='c', nominated_card=Card.baron)
        self.assertEqual(game.players, ['a'])

    def test_baron(self):
        """ This simply tests that the baron can knock a player out. We check
            also that a baron-tie causes no changes. We should of course also
            check that handmaid makes this card essentially a simple discard.
        """
        deck = [ Card.baron, # player a is dealt this card
                 Card.priest, # player b is dealt this card
                 Card.baron, # player c is dealt this card
                 Card.countess, # player d is dealt this card
                 Card.prince, # a draws prince, higher than b's priest
                 Card.prince, # c draws prince, lower than d's countess.
                 ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a', Card.baron, nominated_player='b')
        game.draw_card()
        game.play_turn('c', Card.baron, nominated_player='d')
        self.assertEqual(game.players, ['d', 'a'])
        deck = [ Card.baron, # player a is dealt this card
                 Card.priest, # player b is dealt this card
                 Card.baron, # player c is dealt this card
                 Card.prince, # player d is dealt this card
                 Card.prince, # a draws prince, higher than b's priest,
                              # but the same as d's prince.
                 ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a', Card.baron, nominated_player='d')
        # Both a and d still in the game due to the drawn baron showdown.
        self.assertEqual(game.players, ['b', 'c', 'd', 'a'])

    def test_prince(self):
        """ This tests the prince has the desired effect, we will also check
            that you can prince yourself.
        """
        pass
