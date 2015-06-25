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
        self.handmaided = set()
        self.hands = {x: self.deck.pop(0) for x in self.players}
        self.draw_card()

    def take_top_card(self):
        return self.deck.pop(0)

    def draw_card(self):
        player = self.players.pop(0)
        card = self.hands[player]
        new_card = self.take_top_card()
        self.on_turn = player, card, new_card

    def play_turn(self, who, card, nominated_player=None, nominated_card=None):
        player, card_one, card_two = self.on_turn
        if player != who:
            raise Exception("It's not your turn: " + player + " " + str(self.players))
        if card not in [card_one, card_two]:
            raise Exception("Illegal attempt to play a card you do not have.")
        kept_card = card_two if card == card_one else card_one

        # If the player is handmaided, they are now not handmaided.
        self.handmaided.discard(player)

        if card == Card.guard:
            if nominated_player is None:
                raise Exception("You have to nominate a player to play the guard")
            if nominated_card is None:
                raise Exception("You have to nominate a card to play the guard")
            if nominated_card == Card.guard:
                raise Exception("You cannot guard a guard")
            if nominated_player in self.handmaided:
                raise Exception("You cannot guard a handmaided player.")
            nominated_players_card = self.hands[nominated_player]
            if nominated_card == nominated_players_card:
                # Nominated player is out of the game
                self.players.remove(nominated_player)

        if card == Card.baron:
            if nominated_player is None:
                raise Exception("You have to nominate a player to play the baron.")
            if nominated_player not in self.players:
                raise Exception("You have to baron against a player still in the game.")
            if nominated_player in self.handmaided:
                raise Exception("You cannot baron a handmaided player.")
            opponents_card = self.hands[nominated_player]
            if kept_card > opponents_card:
                self.players.remove(nominated_player)
            elif opponents_card > kept_card:
                # Do nothing, but the current player is out of the game so we
                # return without placing the current player in players list
                return
            # If the cards are equal nothing happens.

        if card == Card.handmaid:
            self.handmaided.add(player)

        if card == Card.prince:
            if nominated_player is None:
                raise Exception("You have to nominate a player to play the prince.")
            if nominated_player not in [player] + self.players:
                raise Exception("You have to prince against a player still in the game.")
            if nominated_player in self.handmaided:
                raise Exception("You cannot prince a handmaided player.")
            # Note: unlike the king below you cannot simply discard the prince,
            # if all other players are handmaided you have to prince yourself.
            if nominated_player == player:
                if kept_card == Card.princess:
                    # Oh oh, you're out of the game! Return without placing the
                    # current player in player list
                    return
                new_card = self.take_top_card()
                kept_card = new_card
            else:
                if self.hands[nominated_player] == Card.princess:
                    # Oh oh, that player is forced to discard the princess and
                    # is hence out of the game.
                    self.players.remove(nominated_player)
                else:
                    # Otherwise give them a new card.
                    new_card = self.take_top_card()
                    self.hands[nominated_player] = new_card

        if card == Card.king:
            # Note, if you are forced to swap the princess I don't think this
            # counts as discarding it, so you're not out.
            if nominated_player is None:
                if all(p in self.handmaided for p in self.players):
                    # Okay so fine there is no-one you can play the king against
                    # hence it becomes a simple discard.
                    pass
                else:
                    raise Exception("You have to nominate a player to play the king")
            elif nominated_player not in self.players:
                raise Exception("You have to king against a player still in the game.")
            elif nominated_player in self.handmaided:
                raise Exception("You cannot king a handmaided players, must nominate None.")
            else:
                opponents_card = self.hands[nominated_player]
                kept_card, self.hands[nominated_player] = opponents_card, kept_card

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

    def test_handmaid(self):
        """ There is actually no real test to do on the handmaid, if the
            front-end does not allow invalid moves then we should never
            apply another card to a player protected by a handmaid. Here
            we mostly just make sure that the correct players are protected
            under a handmaid and that we raise an exception if we attempt to
            play another card against a handmaid.
        """
        deck = [ Card.handmaid, # player a is dealt this card
                 Card.baron, # player b is dealt this card
                 Card.guard, # player c is dealt this card
                 Card.countess, # player d is dealt this card
                 Card.prince, # a draws this card
                 Card.prince, # b draws this card
                 Card.guard, # d draws this card.
                 Card.guard, # a draws a guard
                 Card.handmaid, # d draws a handmaid
                 Card.king, # a draws a king
                 ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a', Card.handmaid)
        self.assertEqual(set(['a']), game.handmaided)
        game.draw_card()
        # Assert that 'b' cannot baron 'a'
        with self.assertRaises(Exception):
            game.play_turn('b', Card.baron, nominated_player='a')
        # But they can baron 'c' and will win as prince > guard
        game.play_turn('b', Card.baron, nominated_player='c')
        self.assertEqual(['d', 'a', 'b'], game.players)
        # a is still handmaided
        self.assertEqual(set(['a']), game.handmaided)
        # 'd' draws and plays the guard and kills b
        game.draw_card()
        game.play_turn('d', Card.guard, nominated_player='b', nominated_card=Card.prince)
        self.assertEqual(['a', 'd'], game.players)
        # 'a' draws and plays a guard, but does not manage to kill 'd' we check
        # that 'a' is no longer handmaided
        game.draw_card()
        game.play_turn('a', Card.guard, nominated_player='d', nominated_card=Card.princess)
        self.assertEqual(set(), game.handmaided)
        # 'd' draws and plays a handmaid
        game.draw_card()
        game.play_turn('d', Card.handmaid)
        self.assertIn('d', game.handmaided)
        # 'a' draws a king, and plays it but it has no effect because 'd',
        # the only other player, is handmaided. Here we show that attempting to
        # king 'd' results in an exception so instead we king None.
        game.draw_card()
        with self.assertRaises(Exception):
            game.play_turn('a', Card.king, nominated_player='d')
        game.play_turn('a', Card.king, nominated_player=None)
        # We check the state of the game is as we expect:
        self.assertEqual(['d', 'a'], game.players)
        self.assertEqual(Card.prince, game.hands['a'])
        self.assertEqual(Card.countess, game.hands['d'])

    def test_prince(self):
        """ This tests the prince has the desired effect, we will also check
            that you can prince yourself.
        """
        deck = [ Card.prince, # player a is dealt this card
                 Card.guard, # player b is dealt this card
                 Card.prince, # player c is dealt this card
                 Card.guard, # player d is dealt this card
                 Card.guard, # player a draws this card
                 Card.princess, # player b draws this when princed by 'a'
                 Card.countess, # player b draws this card on their turn
                 Card.handmaid, # player c draws this card on their turn
                 Card.king # player c princes themselves and draws this card.
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a', Card.prince, nominated_player='b')
        # Assert that 'b' now has the princess not the guard they were dealt.
        self.assertEqual(game.hands['b'], Card.princess)
        game.draw_card()
        game.play_turn('b', Card.countess)
        game.draw_card()
        game.play_turn('c', Card.prince, nominated_player='c')
        # So now 'b' should still have the prince and 'c' should have a king.
        self.assertEqual(game.hands['b'], Card.princess)
        self.assertEqual(game.hands['c'], Card.king)

    def test_king(self):
        deck = [ Card.king, # player a is dealt this card
                 Card.guard, # player b is dealt this card
                 Card.prince, # player c is dealt this card
                 Card.princess, # player d is dealt this card
                 Card.guard, # player a draws this card
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a', Card.king, nominated_player='d')
        self.assertEqual(game.hands['a'], Card.princess)
        self.assertEqual(game.hands['d'], Card.guard)
