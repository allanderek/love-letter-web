"""A simple web application to play the game 'love letter'."""

from enum import IntEnum
import random
from collections import namedtuple

import unittest

import flask
from flask import request, url_for
import sqlalchemy
import sqlalchemy.orm
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
import flask_wtf
from wtforms import HiddenField, IntegerField, StringField
from wtforms.validators import DataRequired, Email

import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Configuration(object):
    SECRET_KEY = b'7a\xe1f\x17\xc9C\xcb*\x85\xc1\x95G\x97\x03\xa3D\xd3F\xcf\x03\xf3\x99>'  # noqa
    LIVE_SERVER_PORT = 5000
    database_file = os.path.join(basedir, '../../db.sqlite')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + database_file
application = flask.Flask(__name__)
application.config.from_object(Configuration)

database = SQLAlchemy(application)


class DBLightProfile(database.Model):
    id = database.Column(database.Integer, primary_key=True)
    secret = database.Column(database.Integer)
    nickname = database.Column(database.String(128))
    gamename = database.Column(database.String(128))
    game_id = database.Column(database.Integer, database.ForeignKey('game.id'))

    def __init__(self, gamename):
        self.gamename = gamename
        self.nickname = gamename
        self.secret = random.getrandbits(48)


def create_spectator():
    profile = DBLightProfile('')
    return profile


class DBGame(database.Model):
    __tablename__ = 'game'
    id = database.Column(database.Integer, primary_key=True)
    num_players = database.Column(database.Integer)
    players = database.relationship('DBLightProfile')

    state_log = database.Column(database.String(2048))
    # Slight shame that this is not a computed value but one that we have to
    # keep track of and update whenever a player joins a game. However this
    # makes the query for open games a simple filter. Note, I have not
    # benchmarked this so perhaps querying all games and post-filtering for
    # those that have not started is faster (but likely not when we have a large
    # number of games, in particular a large number of finished games).
    game_started = database.Column(database.Boolean, default=False)

    @property
    def secrets(self):
        return {p.secret: p for p in self.players}

    def player_taken(self, player):
        return any(p.gamename == player for p in self.players)

    def take_player(self, player):
        profile = DBLightProfile(player)
        self.players.append(profile)
        database.session.commit()
        self.game_started = len(self.players) == self.num_players
        return profile.secret

    def is_player(self, secret):
        return secret in self.secrets


def create_database_game():
    """ Create a game in the database. """
    game = Game(['a', 'b', 'c', 'd'])
    state_log = game.serialise_game()
    dbgame = DBGame(num_players=4, state_log=state_log)
    database.session.add(dbgame)
    database.session.commit()
    return dbgame


@application.template_test('plural')
def is_plural(container):
    return len(container) > 1


def redirect_url(default='frontpage'):
    """ A simple helper function to redirect the user back to where they came.

        See: http://flask.pocoo.org/docs/0.10/reqcontext/ and also here:
        http://stackoverflow.com/questions/14277067/redirect-back-in-flask
    """

    return request.args.get('next') or request.referrer or url_for(default)


@application.route("/")
def frontpage():
    return flask.render_template('frontpage.html')


@application.route('/startgame')
def startgame():
    # TODO: The only thing about this is, that I don't really want people
    # accidentally refreshing and starting multiple games, though having said
    # that, those open games should show up in the open-games list.
    db_game = create_database_game()
    url = flask.url_for('viewgame', game_no=db_game.id)
    return flask.redirect(url)


@application.route('/opengames')
def opengames():
    try:
        filter = sqlalchemy.or_(DBGame.game_started.is_(False))
        open_games = database.session.query(DBGame).filter(filter)
    except SQLAlchemyError:
        flask.flash("There was some database error. Sorry, our fault.")
        return flask.redirect('/')
    return flask.render_template('opengames.html', open_games=open_games)


@application.route('/joingame/<int:game_no>/<player>')
def joingame(game_no, player):
    try:
        db_game = database.session.query(DBGame).filter_by(id=game_no).one()
    except SQLAlchemyError:
        flask.flash("Game #{} not found".format(game_no))
        return flask.redirect(redirect_url())
    if db_game.player_taken(player):
        flask.flash("Player {0} has already been taken!".format(player))
        return flask.redirect(redirect_url())
    new_secret = db_game.take_player(player)
    database.session.commit()
    # TODO: we have to actually tell the user about this URL.
    url = flask.url_for('viewgame', game_no=db_game.id, secret=new_secret)
    return flask.redirect(url)


class SecretProfileForm(flask_wtf.Form):
    nickname = StringField("Your new display name", validators=[DataRequired()])


@application.route('/updateprofile/<int:game_no>/<int:profile_id>/<int:secret>',
                   methods=['POST'])
def updateprofile(game_no, profile_id, secret):
    try:
        query = database.session.query(DBLightProfile)
        profile = query.filter_by(id=profile_id).one()
    except SQLAlchemyError:
        flask.flash("Light profile not found for {0}".format(profile_id))
        return flask.redirect(redirect_url())
    if profile.secret != secret:
        flask.flash("You do not have the correct secret to update that profile")
        return flask.redirect(redirect_url())
    form = SecretProfileForm()
    if form.validate_on_submit():
        profile.nickname = form.nickname.data
        database.session.commit()
        return flask.redirect(redirect_url())
    flask.flash("Updated profile form no validated!")
    return flask.redirect(redirect_url())


@application.route('/viewgame/<int:game_no>')  # noqa
@application.route('/viewgame/<int:game_no>/<int:secret>')
def viewgame(game_no, secret=None):
    try:
        db_game = database.session.query(DBGame).filter_by(id=game_no).one()
    except SQLAlchemyError:
        flask.flash("Game #{} not found".format(game_no))
        return flask.redirect(redirect_url())
    player = create_spectator()
    profile_form = None
    if secret is not None:
        try:
            player = db_game.secrets[secret]
        except KeyError:
            flask.flash("You are not in this game! Secret key invalid.")
            secret = None
        else:
            profile_form = SecretProfileForm()

    game = None
    possible_moves = None
    your_hand = None
    if db_game.game_started:
        game = Game(players=['a', 'b', 'c', 'd'], log=db_game.state_log)
        gamename = player.gamename
        if not game.is_game_finished() and game.is_players_turn(gamename):
            possible_moves = game.available_moves()
            your_hand = None  # viewgame will use the possible_moves instead
        else:
            possible_moves = None
            # The player is in this game but they may be eliminated hence
            # their hand will not be in game.hands.
            your_hand = game.hands.get(gamename, None)
    return flask.render_template('viewgame.html', game=game, db_game=db_game,
                                 game_id=db_game.id, profile_form=profile_form,
                                 secret=secret, player=player,
                                 possible_moves=possible_moves,
                                 your_hand=your_hand
                                 )


@application.route('/playcard/<int:game_no>/<int:secret>/<int:card>')  # noqa
@application.route('/playcard/<int:game_no>/<int:secret>/<int:card>/<nom_player>')  # noqa
@application.route('/playcard/<int:game_no>/<int:secret>/<int:card>/<nom_player>/<int:nom_card>')  # noqa
def playcard(game_no, secret, card, nom_player=None, nom_card=None):
    try:
        db_game = database.session.query(DBGame).filter_by(id=game_no).one()
    except SQLAlchemyError:
        flask.flash("Game #{} not found".format(game_no))
        return redirect('/')
    game = Game(players=['a', 'b', 'c', 'd'], log=db_game.state_log)
    try:
        player = db_game.secrets[secret]
    except KeyError:
        flask.flash("You are not in this game! Secret key invalid.")
        return flask.redirect(redirect_url())
    card = Card(int(card))
    nom_card = None if nom_card is None else Card(int(nom_card))
    move = Move(player.gamename, card, nominated_card=nom_card,
                nominated_player=nom_player)
    try:
        game.play_move(move)
    except NotYourTurnException:
        flask.flash("It's not your turn!")
    else:
        db_game.state_log = game.serialise_game()
        database.session.commit()
    return flask.redirect(redirect_url())


class Card(IntEnum):
    princess = 8
    countess = 7
    king = 6
    prince = 5
    handmaid = 4
    baron = 3
    priest = 2
    guard = 1

card_pack = [Card.princess, Card.countess, Card.king, Card.prince,
             Card.handmaid, Card.handmaid, Card.baron, Card.baron,
             Card.priest, Card.priest,
             Card.guard, Card.guard, Card.guard, Card.guard, Card.guard]


class NotYourTurnException(Exception):
    """ An exception to raise when a player attempts to play out of turn."""
    pass


class CountessForcedException(Exception):
    """ An exception to be raised whenever a player attempts to play a king or
        a prince when holding on to the Countess
    """
    pass


class NoNominatedPlayerException(Exception):
    """An exception to raise whenever a player does not nominate a player.
    Some cards, namely, the guard, priest, baron, prince and king require that
    you nominate a player (unless all other players are handmaided). This is
    the exception to raise if a player fails to do so.
    """
    pass


class GameFinished(Exception):
    """An exception to raise when the game is over.
    The game is over either because there is only a single player left,
    or because there are no cards left to draw.
    """
    pass


def format_none(value, format_fun=str):
    """ Utility function to format a value as a string when the value may be
    'None', in which case we want the empty string.
    """
    return '' if value is None else format_fun(value)


class Move(object):
    """A class for describing a move made in the game."""

    def __init__(self, who, card, nominated_player=None, nominated_card=None):
        """Simple constructor. Nominated_player and nominated_card are optional
        since not all moves require either.
        """
        self.player = who
        self.card = card
        self.nominated_player = nominated_player
        self.nominated_card = nominated_card

    def to_log_string(self):
        nom_player = format_none(self.nominated_player, str)
        nom_card = format_none(self.nominated_card,
                               format_fun=lambda x: str(x.value))
        log_entry = ",".join([self.player,
                              str(self.card.value),
                              nom_player,
                              nom_card])
        return log_entry

    def obscure(self, player):
        """ Moves are always visible by everyone."""
        return self


class DiscardLog(object):
    def __init__(self, player, card):
        self.player = player
        self.card = card

    def to_log_string(self):
        return '{0}-{1}'.format(self.player, self.card)

    def obscure(self, player):
        """Discards are always visible by everyone so this is simple."""
        return self


class PickupLog(object):
    def __init__(self, player, card):
        self.player = player
        self.card = card

    def to_log_string(self):
        return '{0}:{1}'.format(self.player, self.card)

    def obscure(self, player):
        return self if player == self.player else __class__(self.player, '?')


class PriestLog(object):
    def __init__(self, player_shows, player_sees, card):
        self.player_shows = player_shows
        self.player_sees = player_sees
        self.card = card

    def to_log_string(self):
        return '{0};{1};{2}'.format(self.player_shows, self.player_sees,
                                    self.card)

    def obscure(self, player):
        if player in [self.player_shows, self.player_sees]:
            return self
        else:
            return __class__(self.player_shows, self.player_sees, '?')

PossibleMoves = namedtuple('PossibleMove', ["card", "moves"])


class Game(object):
    """The main game class representing a game currently in play."""
    def __init__(self, players, deck=None, discarded=None, log=None):
        self.players = players
        self.handmaided = set()
        self.out_players = set()
        self.hands = dict()
        self.log = []
        self.winners = None
        self.winning_card = None
        self.on_turn = None

        if log is None:
            if deck is None:
                # If we are not setting the deck then we assume that we are
                # wanting a random deck so we randomly shuffle the cards and
                # choose a random one as the discarded.
                self.deck = card_pack.copy()
                random.shuffle(self.deck)
                self.discarded = self.deck.pop(0)
            else:
                # If we are setting the deck we assume that we are in a test
                # mode so we set the known deck and either we know that our test
                # does not need a discarded card or we want to know what it is.
                self.deck = deck
                self.discarded = discarded

            # Begin the game by dealing a card to each player
            for p in self.players:
                card = self.deck.pop(0)
                self.hands[p] = card
                self.log.append(PickupLog(p, card))
            # And drawing a card for the first player:
            self.draw_card()
        else:
            log_lines = log.split("\n")
            for l in log_lines[:4]:
                player, card = self.parse_drawcard(l)
                self.hands[player] = card
                self.log.append(PickupLog(player, card))

            deck_lines = [self.parse_drawcard(l)
                          for l in log_lines[4:] if ':' in l]
            play_lines = [self.parse_action(l) for l in log_lines if ',' in l]

            self.deck = [c for _, c in deck_lines]

            rest_of_deck = card_pack.copy()
            for c in self.deck:
                rest_of_deck.remove(c)
            for c in self.hands.values():
                rest_of_deck.remove(c)
            random.shuffle(rest_of_deck)
            # It is possible there is no discarded because all the cards were
            # used up. This would happen if we are loading the log of a game
            # that finished with someone playing the prince forcing someone
            # else to take the discarded card. So we have to check that the
            # rest of the deck is not empty.
            if rest_of_deck:
                self.discarded = rest_of_deck.pop()
            self.deck += rest_of_deck
            self.draw_card()
            for move in play_lines:
                self.play_move(move)

    def parse_drawcard(self, line):
        return (line[0], Card(int(line[2])))

    def parse_action(self, line):
        fields = line.split(",")
        card = Card(int(fields[1]))
        nom_player = None if fields[2] == '' else fields[2]
        nom_card = None if fields[3] == '' else Card(int(fields[3]))
        return Move(fields[0], card,
                    nominated_player=nom_player, nominated_card=nom_card)

    def serialise_game(self, player=None):
        """ Serialise the game, if player is given then the serialised log is
        sanitised such that the player cannot see information that they should
        not. However, this is mostly for testing purposes, in general
        serialise_game is used internally to store the game in the database and
        not to pass information to the players.
        """
        log = self.log_for_player(player) if player else self.log
        return "\n".join([l.to_log_string() for l in log])

    def log_for_player(self, player):
        """Returns a log sanitised by hiding information not available to
           to everyone, unless it is available to the given player. Note that,
           this means if you provide a player not in the game (eg. None) then
           this will return a log which hides all non-public information.
        """
        return [l.obscure(player) for l in self.log]

    def take_top_card(self):
        return self.deck.pop(0)

    def draw_card(self, card=None):
        """ You can draw a known card, this is useful for restoring a game from
            a log.
        """
        assert self.on_turn is None
        if card is None:
            if self.is_game_finished():
                raise GameFinished()
            else:
                card = self.take_top_card()
        player = self.players.pop(0)
        # If the player is handmaided, they are now not handmaided.
        self.handmaided.discard(player)
        old_card = self.hands[player]
        self.on_turn = player, old_card, card
        self.log.append(PickupLog(player, card))

    def live_players(self):
        on_turn = [] if self.on_turn is None else [self.on_turn[0]]
        return on_turn + self.players

    def is_game_finished(self):
        completed_deck = self.on_turn is None and not self.deck
        one_player = len(self.live_players()) <= 1
        return completed_deck or one_player

    def is_players_turn(self, player):
        return self.on_turn is not None and self.on_turn[0] == player

    def _available_moves_for_card(self, player, card, other_card):
        """ Return the moves available for the first given card. The second
            given card is only included so that the countess rules can be
            applied to the prince and king cards, but note we are not
            considering any moves playable by the second given card.
        """
        if card in [Card.prince, Card.king] and other_card == Card.countess:
            # It may seem strange that we do not return the countess move but
            # that should be returned by the other call to this method.
            return []
        elif card == Card.guard:
            # You cannot guard a guard. You can guess any other card, here we
            # do not prevent you from being stupid and guessing something that
            # has already been discarded.
            guessable_cards = list(Card)
            guessable_cards.remove(Card.guard)
            open_players = [p for p in self.players if p not in self.handmaided]
            if open_players:
                return [Move(player, card, nominated_player=p, nominated_card=c)
                        for p in open_players for c in guessable_cards]
            else:
                # All opponents are handmaided, but you can discard the guard.
                return [Move(player, card)]
        elif card in [Card.priest, Card.baron, Card.king]:
            # If all other players are handmaided you can simply discard the
            # card. This means that you cannot choose to discard these cards
            # if not all remaining players are handmaided, which would be useful
            # if you for example have two barons, or a king and the princess.
            open_players = [p for p in self.players if p not in self.handmaided]
            if not open_players:
                return [Move(player, card)]
            return [Move(player, card, nominated_player=p)
                    for p in open_players]
        elif card == Card.prince:
            # Slightly different from the priest, baron and king above
            # in that you must always prince someone and that someone can
            # always be you.
            open_players = [p for p in self.players if p not in self.handmaided]
            return [Move(player, card, nominated_player=p)
                    for p in [player] + open_players]
        elif card in [Card.handmaid, Card.countess, Card.princess]:
            # You can always play any of these three cards, of course playing
            # the princess will lose you the game.
            return [Move(player, card)]
        raise Exception("Invalid card for available moves.")

    def available_moves(self):
        player, card_one, card_two = self.on_turn
        moves_one = self._available_moves_for_card(player, card_one, card_two)
        pmoves_one = PossibleMoves(card=card_one, moves=moves_one)
        moves_two = self._available_moves_for_card(player, card_two, card_one)
        pmoves_two = PossibleMoves(card=card_two, moves=moves_two)
        return (pmoves_one, pmoves_two)

    def play_turn(self, move_string):
        self.play_move(self.parse_action(move_string))

    def play_move(self, move):
        who = move.player
        card = move.card
        nominated_player = move.nominated_player
        nominated_card = move.nominated_card
        # In theory we should set self.on_turn to None, but we back-out of some
        # moves because it is illegal and for testing purposes it is nice to be
        # able to continue with the game after a failed move. But it would be
        # nice to be able to make sure a player is out of the game, which simply
        # inspecting self.players does not quite do.
        player, card_one, card_two = self.on_turn

        # Some cards force others to discard their cards, possibly by being
        # out of the game. The prince forces you to discard and pickup, but we
        # do not want to log these events as occuring *before* the current play.
        # So we store them up and then log them only after the current play is
        # logged.
        discard_logs = []

        def log_discard(player, out_card):
            discard_logs.append(DiscardLog(player, out_card))

        def log_extra_pickup(pickup_player, extra_card):
            discard_logs.append(PickupLog(pickup_player, extra_card))

        def log_play():
            """ We define this as a method rather than simply doing this now,
                because we may back out of this if the move is not valid.
            """
            self.log.append(move)
            for l in discard_logs:
                self.log.append(l)

        def eliminate_player(eliminated):
            self.hands[eliminated] = None
            self.out_players.add(eliminated)
            if eliminated != player:
                self.players.remove(eliminated)

        all_opponents_handmaided = all(p in self.handmaided
                                       for p in self.players)

        if player != who:
            msg_fmt = "It's not your turn: {0} != {1}, {2}"
            message = msg_fmt.format(player.gamename, who, str(self.players))
            raise NotYourTurnException(message)
        if card not in [card_one, card_two]:
            raise Exception("Illegal attempt to play a card you do not have.")
        kept_card = card_two if card == card_one else card_one

        if card == Card.guard:
            if nominated_player is None:
                if not all_opponents_handmaided:
                    raise NoNominatedPlayerException()

                # Otherwise that's fine then, we just discard the card and
                # carry on. We possibly should also check that the nominated
                # card is also None.
            elif nominated_player not in self.players:
                raise Exception("You cannot guard someone who is already out")
            elif nominated_card is None:
                raise Exception("You have to nominate a card to play the guard")
            elif nominated_card == Card.guard:
                raise Exception("You cannot guard a guard")
            elif nominated_player in self.handmaided:
                raise Exception("You cannot guard a handmaided player.")
            else:
                nominated_players_card = self.hands[nominated_player]
                if nominated_card == nominated_players_card:
                    # Nominated player is out of the game
                    log_discard(nominated_player, self.hands[nominated_player])
                    eliminate_player(nominated_player)

        elif card == Card.priest:
            # For a priest card we have to log who has been priested by whom,
            # so that in the player's (the one priesting) log they will see the
            # card shown to them. In addition of course we have to check that
            # you are not attempting to preist a player who is handmaided
            if nominated_player is None:
                if all_opponents_handmaided:
                    # That's fine then, we just discard the card and carry on
                    # We possibly should also check that the nominated card is
                    # also None.
                    pass
                else:
                    raise NoNominatedPlayerException()
            elif nominated_player not in self.players:
                raise Exception("You must baron a player still in the game.")
            elif nominated_player in self.handmaided:
                raise Exception("You cannot baron a handmaided player.")
            else:
                # In this case we have a valid use of the priest card that is
                # not simply discarding because all opponents are handmaided.
                seen_card = self.hands[nominated_player]
                log_entry = PriestLog(nominated_player, player, seen_card)
                discard_logs.append(log_entry)
        elif card == Card.baron:
            if nominated_player is None:
                if all_opponents_handmaided:
                    # That's fine then, we just discard the card and carry on
                    # We possibly should also check that the nominated card is
                    # also None.
                    pass
                else:
                    raise NoNominatedPlayerException()
            elif nominated_player not in self.players:
                raise Exception("You must baron a player still in the game.")
            elif nominated_player in self.handmaided:
                raise Exception("You cannot baron a handmaided player.")
            else:
                opponents_card = self.hands[nominated_player]
                if kept_card > opponents_card:
                    log_discard(nominated_player, opponents_card)
                    eliminate_player(nominated_player)
                elif opponents_card > kept_card:
                    # The current player is out of the game
                    log_discard(player, kept_card)
                    eliminate_player(player)
                # If the cards are equal nothing happens.

        elif card == Card.handmaid:
            self.handmaided.add(player)

        elif card == Card.prince:
            if kept_card == Card.countess:
                raise CountessForcedException("You have a prince")
            elif nominated_player is None:
                raise NoNominatedPlayerException()
            elif nominated_player not in [player] + self.players:
                raise Exception("You must prince a player still in the game.")
            elif nominated_player in self.handmaided:
                raise Exception("You cannot prince a handmaided player.")
            # Note: unlike the king below you cannot simply discard the prince,
            # if all other players are handmaided you have to prince yourself.
            elif nominated_player == player:
                log_discard(nominated_player, kept_card)
                if kept_card == Card.princess:
                    # Oh oh, you're out of the game!
                    eliminate_player(player)
                else:
                    try:
                        new_card = self.take_top_card()
                    except IndexError:
                        new_card = self.discarded
                    log_extra_pickup(player, new_card)
                    kept_card = new_card
            else:
                discarded = self.hands[nominated_player]
                log_discard(nominated_player, discarded)
                if discarded == Card.princess:
                    # Oh oh, that player is forced to discard the princess and
                    # is hence out of the game.
                    eliminate_player(nominated_player)
                else:
                    # Otherwise give them a new card. Note that if the deck is
                    # empty they are given the card that was discarded from the
                    # deck at the start (to ensure there is not total knowledge
                    # of the deck).
                    try:
                        new_card = self.take_top_card()
                    except IndexError:
                        new_card = self.discarded
                    log_extra_pickup(nominated_player, new_card)
                    self.hands[nominated_player] = new_card

        elif card == Card.king:
            # Note, if you are forced to swap the princess I don't think this
            # counts as discarding it, so you're not out, so we do not check
            # for that here.

            if kept_card == Card.countess:
                raise CountessForcedException("You have a king")
            elif nominated_player is None:
                if not all_opponents_handmaided:
                    raise NoNominatedPlayerException()
                # If all opponents are handmaided then playing the king
                # becomes a simple discard.
            elif nominated_player not in self.players:
                raise Exception("You must king a player still in the game.")
            elif nominated_player in self.handmaided:
                raise Exception("You cannot king a handmaided player.")
            else:
                # Swap the cards, not using a,b = b,a for pep8 reasons.
                opponents_card = self.hands[nominated_player]
                self.hands[nominated_player] = kept_card
                kept_card = opponents_card

        elif card == Card.countess:
            # This is fine, we need to check above that a player never manages
            # to avoid discarding the countess when they hold the prince or the
            # king, but discarding the countess is always fine, but has no
            # effect, other than to add the discard.
            pass

        elif card == Card.princess:
            # The player is out, so do not append them to the back of the
            # players list.
            eliminate_player(player)

        log_play()
        if player not in self.out_players:
            self.hands[player] = kept_card
            self.players.append(player)
        self.on_turn = None
        if self.is_game_finished():
            for p in self.players:
                if self.winning_card is None:
                    self.winning_card = self.hands[p]
                    self.winners = set(p)
                elif self.hands[p] > self.winning_card:
                    self.winning_card = self.hands[p]
                    self.winners = set(p)
                elif self.hands[p] == self.winning_card:
                    self.winners.add(p)
        else:
            self.draw_card()


class GameTest(unittest.TestCase):
    def test_guard_wins(self):
        """ In this test we check that a player with a guard can knock out
            the other players. This will be more or less the shortest game
            possible in which player 1 knocks out player 2, player 3 knocks
            out player 4 and then player 1 again knocks out player 2.
        """
        # We set the deck so that we know what comes next.
        deck = [Card.guard,  # Player 1's dealt card.
                Card.priest,  # Player 2's dealt card, which p1 will guess.
                Card.guard,  # Player 3's dealt card.
                Card.priest,  # Player 4's dealt card which p3 will guess.
                Card.guard,  # Player 1's drawn card.
                Card.baron,  # Player 3's drawn card which p1 will guess and win
                Card.baron  # Player 1 still needs to draw a card.
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,1,b,2')
        game.play_turn('c,1,d,2')
        game.play_turn('a,1,c,3')
        self.assertEqual(game.players, ['a'])
        expected_log = ("a:1\nb:2\nc:1\nd:2\na:1\na,1,b,2\nb-2\nc:3\nc,1,d,2\n"
                        "d-2\na:3\na,1,c,3\nc-3")
        self.assertEqual(game.serialise_game(), expected_log)
        # Now we do an expected log for each player.
        expected_log = ("a:1\nb:?\nc:?\nd:?\na:1\na,1,b,2\nb-2\nc:?\nc,1,d,2\n"
                        "d-2\na:3\na,1,c,3\nc-3")
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = ("a:?\nb:2\nc:?\nd:?\na:?\na,1,b,2\nb-2\nc:?\nc,1,d,2\n"
                        "d-2\na:?\na,1,c,3\nc-3")
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = ("a:?\nb:?\nc:1\nd:?\na:?\na,1,b,2\nb-2\nc:3\nc,1,d,2\n"
                        "d-2\na:?\na,1,c,3\nc-3")
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = ("a:?\nb:?\nc:?\nd:2\na:?\na,1,b,2\nb-2\nc:?\nc,1,d,2\n"
                        "d-2\na:?\na,1,c,3\nc-3")
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def test_priest(self):
        """ Priests do not really affect the game state, all it means is that
        one player now knows what another player currently holds. However we
        can check the log is correctly updated with this information, since the
        log will be shown to each player.
        """
        deck = [Card.priest,  # Player 1's dealt card
                Card.countess,  # Player 2's dealt card
                Card.guard,  # Player 3's dealt card
                Card.king,  # Player 4's dealt card
                Card.guard,  # Player 1's drawn card
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,2,b,')
        self.assertEqual(game.players, ['b', 'c', 'd', 'a'])
        expected_log = "a:2\nb:7\nc:1\nd:6\na:1\na,2,b,\nb;a;7"
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = "a:2\nb:?\nc:?\nd:?\na:1\na,2,b,\nb;a;7"
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:7\nc:?\nd:?\na:?\na,2,b,\nb;a;7"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:1\nd:?\na:?\na,2,b,\nb;a;?"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:6\na:?\na,2,b,\nb;a;?"
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def test_baron(self):
        """ This simply tests that the baron can knock a player out. We check
            also that a baron-tie causes no changes. We should of course also
            check that handmaid makes this card essentially a simple discard.
        """
        deck = [Card.baron,  # player a is dealt this card
                Card.priest,  # player b is dealt this card
                Card.baron,  # player c is dealt this card
                Card.countess,  # player d is dealt this card
                Card.prince,  # a draws prince, higher than b's priest
                Card.prince,  # c draws prince, lower than d's countess.
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,3,b,')
        game.play_turn('c,3,d,')
        self.assertEqual(game.players, ['d', 'a'])
        expected_log = "a:3\nb:2\nc:3\nd:7\na:5\na,3,b,\nb-2\nc:5\nc,3,d,\nc-5"
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = "a:3\nb:?\nc:?\nd:?\na:5\na,3,b,\nb-2\nc:?\nc,3,d,\nc-5"
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:2\nc:?\nd:?\na:?\na,3,b,\nb-2\nc:?\nc,3,d,\nc-5"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:3\nd:?\na:?\na,3,b,\nb-2\nc:5\nc,3,d,\nc-5"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:7\na:?\na,3,b,\nb-2\nc:?\nc,3,d,\nc-5"
        self.assertEqual(game.serialise_game(player='d'), expected_log)
        deck = [Card.baron,  # player a is dealt this card
                Card.priest,  # player b is dealt this card
                Card.baron,  # player c is dealt this card
                Card.prince,  # player d is dealt this card
                Card.prince,  # a draws prince, higher than b's priest,
                              # but the same as d's prince.
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,3,d,')
        # Both a and d still in the game due to the drawn baron showdown.
        self.assertEqual(game.players, ['b', 'c', 'd', 'a'])
        expected_log = "a:3\nb:2\nc:3\nd:5\na:5\na,3,d,"
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = "a:3\nb:?\nc:?\nd:?\na:5\na,3,d,"
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:2\nc:?\nd:?\na:?\na,3,d,"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:3\nd:?\na:?\na,3,d,"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:5\na:?\na,3,d,"
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def test_handmaid(self):
        """ There is actually no real test to do on the handmaid, if the
            front-end does not allow invalid moves then we should never
            apply another card to a player protected by a handmaid. Here
            we mostly just make sure that the correct players are protected
            under a handmaid and that we raise an exception if we attempt to
            play another card against a handmaid.
        """
        deck = [Card.handmaid,  # player a is dealt this card
                Card.baron,  # player b is dealt this card
                Card.guard,  # player c is dealt this card
                Card.countess,  # player d is dealt this card
                Card.prince,  # a draws this card
                Card.prince,  # b draws this card
                Card.guard,  # d draws this card.
                Card.guard,  # a draws a guard
                Card.handmaid,  # d draws a handmaid
                Card.king,  # a draws a king
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,4,,')
        self.assertEqual(set(['a']), game.handmaided)
        # Assert that 'b' cannot baron 'a'
        with self.assertRaises(Exception):
            game.play_turn('b,3,a,')
        # But they can baron 'c' and will win as prince > guard
        game.play_turn('b,3,c,')
        self.assertEqual(['d', 'a', 'b'], game.live_players())
        # a is still handmaided
        self.assertEqual(set(['a']), game.handmaided)
        # 'd' draws and plays the guard and kills b
        game.play_turn('d,1,b,5')
        self.assertEqual(['a', 'd'], game.live_players())
        # 'a' draws and plays a guard, but does not manage to kill 'd' we check
        # that 'a' is no longer handmaided
        game.play_turn('a,1,d,8')
        self.assertEqual(set(), game.handmaided)
        # 'd' draws and plays a handmaid
        game.play_turn('d,4,,')
        self.assertIn('d', game.handmaided)
        # 'a' draws a king, and plays it but it has no effect because 'd',
        # the only other player, is handmaided. Here we show that attempting to
        # king 'd' results in an exception so instead we king None.
        with self.assertRaises(Exception):
            game.play_turn('a,6,d,')
        game.play_turn('a,6,,')
        # We check the state of the game is as we expect:
        self.assertEqual(['d', 'a'], game.players)
        self.assertEqual(Card.prince, game.hands['a'])
        self.assertEqual(Card.countess, game.hands['d'])
        expected_log = ("a:4\nb:3\nc:1\nd:7\na:5\na,4,,\nb:5\nb,3,c,\nc-1\n"
                        "d:1\nd,1,b,5\nb-5\na:1\na,1,d,8\nd:4\nd,4,,\na:6\n"
                        "a,6,,")
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = ("a:4\nb:?\nc:?\nd:?\na:5\na,4,,\nb:?\nb,3,c,\nc-1\n"
                        "d:?\nd,1,b,5\nb-5\na:1\na,1,d,8\nd:?\nd,4,,\na:6\n"
                        "a,6,,")
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = ("a:?\nb:3\nc:?\nd:?\na:?\na,4,,\nb:5\nb,3,c,\nc-1\n"
                        "d:?\nd,1,b,5\nb-5\na:?\na,1,d,8\nd:?\nd,4,,\na:?\n"
                        "a,6,,")
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = ("a:?\nb:?\nc:1\nd:?\na:?\na,4,,\nb:?\nb,3,c,\nc-1\n"
                        "d:?\nd,1,b,5\nb-5\na:?\na,1,d,8\nd:?\nd,4,,\na:?\n"
                        "a,6,,")
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = ("a:?\nb:?\nc:?\nd:7\na:?\na,4,,\nb:?\nb,3,c,\nc-1\n"
                        "d:1\nd,1,b,5\nb-5\na:?\na,1,d,8\nd:4\nd,4,,\na:?\n"
                        "a,6,,")
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def test_prince(self):
        """ This tests the prince has the desired effect, we will also check
            that you can prince yourself.
        """
        deck = [Card.prince,  # player a is dealt this card
                Card.guard,  # player b is dealt this card
                Card.prince,  # player c is dealt this card
                Card.guard,  # player d is dealt this card
                Card.guard,  # player a draws this card
                Card.princess,  # player b draws this when princed by 'a'
                Card.countess,  # player b draws this card on their turn
                Card.handmaid,  # player c draws this card on their turn
                Card.king  # player c princes themselves and draws this card.
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,5,b,')
        # Assert that 'b' now has the princess not the guard they were dealt.
        self.assertEqual(game.hands['b'], Card.princess)
        game.play_turn('b,7,,')

        # c draws a card and we check that they are able to prince themselves.
        game.play_turn('c,5,c,')
        # So now 'b' should still have the princess and 'c' should have a king.
        self.assertEqual(game.hands['b'], Card.princess)
        self.assertEqual(game.hands['c'], Card.king)
        self.assertEqual(game.players, ['d', 'a', 'b', 'c'])
        expected_log = ("a:5\nb:1\nc:5\nd:1\na:1\na,5,b,\nb-1\nb:8\nb:7\n"
                        "b,7,,\nc:4\nc,5,c,\nc-4\nc:6")
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = ("a:5\nb:?\nc:?\nd:?\na:1\na,5,b,\nb-1\nb:?\nb:?\n"
                        "b,7,,\nc:?\nc,5,c,\nc-4\nc:?")
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = ("a:?\nb:1\nc:?\nd:?\na:?\na,5,b,\nb-1\nb:8\nb:7\n"
                        "b,7,,\nc:?\nc,5,c,\nc-4\nc:?")
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = ("a:?\nb:?\nc:5\nd:?\na:?\na,5,b,\nb-1\nb:?\nb:?\n"
                        "b,7,,\nc:4\nc,5,c,\nc-4\nc:6")
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = ("a:?\nb:?\nc:?\nd:1\na:?\na,5,b,\nb-1\nb:?\nb:?\n"
                        "b,7,,\nc:?\nc,5,c,\nc-4\nc:?")
        self.assertEqual(game.serialise_game(player='d'), expected_log)

        # In another test we make sure that if you attempt to prince someone
        # on the last turn, when there are no cards left we make sure that the
        # card to be taken by the player is the originally discarded card
        # meaning the card discarded from the deck to make sure there is not
        # total knowledge.
        deck = [Card.prince,  # player a is dealt this card
                Card.guard,  # player b is dealt this card
                Card.prince,  # player c is dealt this card
                Card.guard,  # player d is dealt this card
                Card.guard,  # player a draws this card
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck, discarded=Card.princess)
        game.play_turn('a,5,b,')
        self.assertEqual(game.hands['b'], Card.princess)
        expected_log = "a:5\nb:1\nc:5\nd:1\na:1\na,5,b,\nb-1\nb:8"
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = "a:5\nb:?\nc:?\nd:?\na:1\na,5,b,\nb-1\nb:?"
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:1\nc:?\nd:?\na:?\na,5,b,\nb-1\nb:8"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:5\nd:?\na:?\na,5,b,\nb-1\nb:?"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:1\na:?\na,5,b,\nb-1\nb:?"
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def test_king(self):
        deck = [Card.king,  # player a is dealt this card
                Card.guard,  # player b is dealt this card
                Card.prince,  # player c is dealt this card
                Card.princess,  # player d is dealt this card
                Card.guard,  # player a draws this card
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,6,d,')
        self.assertEqual(game.hands['a'], Card.princess)
        self.assertEqual(game.hands['d'], Card.guard)
        expected_log = "a:6\nb:1\nc:5\nd:8\na:1\na,6,d,"
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = "a:6\nb:?\nc:?\nd:?\na:1\na,6,d,"
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:1\nc:?\nd:?\na:?\na,6,d,"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:5\nd:?\na:?\na,6,d,"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:8\na:?\na,6,d,"
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def check_handmaid_discard(self, discard):
        """ For the cards guard, priest, baron, and king if all other players
            are handmaided then you are able to simply discard the card. This
            checks that that is indeed possible.
        """
        deck = [Card.handmaid,  # player a is dealt this card.
                Card.handmaid,  # player b dealt
                Card.handmaid,  # player c dealt
                discard,  # player d dealt
                Card.guard,  # player a draws this card
                Card.guard,  # player b draws this card
                Card.guard,  # player c draws this card
                Card.princess,  # player d draws this card
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        game.play_turn('a,4,,')
        game.play_turn('b,4,,')
        game.play_turn('c,4,,')
        # Before we play it as a discard we attempt to play it properly against
        # a handmaided opponent, which should raise an error:
        with self.assertRaises(Exception):
            game.play_turn('d,{0},a,'.format(str(discard.value)))

        game.play_turn('d,{0},,'.format(str(discard.value)))
        self.assertEqual(['a', 'b', 'c', 'd'], game.players)
        expected_log = ("a:4\nb:4\nc:4\nd:{0}\na:1\na,4,,\nb:1\nb,4,,\nc:1\n"
                        "c,4,,\nd:8\nd,{0},,").format(str(discard.value))
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = ("a:4\nb:?\nc:?\nd:?\na:1\na,4,,\nb:?\nb,4,,\nc:?\n"
                        "c,4,,\nd:?\nd,{0},,").format(str(discard.value))
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = ("a:?\nb:4\nc:?\nd:?\na:?\na,4,,\nb:1\nb,4,,\nc:?\n"
                        "c,4,,\nd:?\nd,{0},,").format(str(discard.value))
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = ("a:?\nb:?\nc:4\nd:?\na:?\na,4,,\nb:?\nb,4,,\nc:1\n"
                        "c,4,,\nd:?\nd,{0},,").format(str(discard.value))
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = ("a:?\nb:?\nc:?\nd:{0}\na:?\na,4,,\nb:?\nb,4,,\nc:?\n"
                        "c,4,,\nd:8\nd,{0},,").format(str(discard.value))
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def test_handmaid_dicard(self):
        for card in [Card.guard, Card.priest, Card.baron, Card.king]:
            self.check_handmaid_discard(card)

    def check_countess(self, prince_or_king):
        """ A very basic test that having the prince or the king in a player's
            hand together with the countess forces that player to discard the
            countess.
        """
        self.assertIn(prince_or_king, [Card.prince, Card.king])
        deck = [Card.countess,  # player a is dealt this card.
                Card.guard,  # player b dealt
                Card.guard,  # player c dealt
                Card.baron,  # player d dealt
                prince_or_king  # player a draws this card
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        # Player a draws a prince/king and attempts to play it, but cannot
        # because they have the countess.
        with self.assertRaises(CountessForcedException):
            game.play_turn('a,{0},d,'.format(str(prince_or_king.value)))
        # So they instead discard the countess
        game.play_turn('a,7,,')
        self.assertEqual(game.hands['a'], prince_or_king)
        self.assertEqual(['b', 'c', 'd', 'a'], game.players)
        expected_log = ("a:7\nb:1\nc:1\nd:3\na:{0}\n"
                        "a,7,,").format(str(prince_or_king.value))
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = ("a:7\nb:?\nc:?\nd:?\na:{0}\n"
                        "a,7,,").format(str(prince_or_king.value))
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:1\nc:?\nd:?\na:?\na,7,,"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:1\nd:?\na:?\na,7,,"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:3\na:?\na,7,,"
        self.assertEqual(game.serialise_game(player='d'), expected_log)

    def test_countess(self):
        self.check_countess(Card.prince)
        self.check_countess(Card.king)

    def test_princess(self):
        deck = [Card.princess,  # player a is dealt this card
                Card.guard,  # player b is dealt this card
                Card.prince,  # player c dealt
                Card.guard,  # player d
                Card.baron,  # player a draws this card
                ]
        players = ['a', 'b', 'c', 'd']
        # The simplest case, player 'a' is dealt the princess and discards it
        # immediately, it might be that we should stop someone doing something
        # obviously stupid, but for now we just follow the rules:
        game = Game(players, deck=deck)
        game.play_turn('a,8,,')
        self.assertNotIn('a', game.players)
        expected_log = "a:8\nb:1\nc:5\nd:1\na:3\na,8,,"
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = "a:8\nb:?\nc:?\nd:?\na:3\na,8,,"
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:1\nc:?\nd:?\na:?\na,8,,"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:5\nd:?\na:?\na,8,,"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:1\na:?\na,8,,"
        self.assertEqual(game.serialise_game(player='d'), expected_log)

        # Now we do a more interesting example in which a player is forced to
        # discard the princess via a prince card.
        deck = [Card.prince,  # player a is dealt this card
                Card.guard,  # player b is dealt this card
                Card.princess,  # player c dealt
                Card.guard,  # player d
                Card.baron,  # player a draws this card
                ]
        players = ['a', 'b', 'c', 'd']
        game = Game(players, deck=deck)
        # So player 'a' princes player 'c' and forces them to discard the
        # princess
        game.play_turn('a,5,c,')
        self.assertNotIn('c', game.players)
        self.assertIn('c', game.out_players)
        expected_log = "a:5\nb:1\nc:8\nd:1\na:3\na,5,c,\nc-8"
        self.assertEqual(game.serialise_game(), expected_log)
        expected_log = "a:5\nb:?\nc:?\nd:?\na:3\na,5,c,\nc-8"
        self.assertEqual(game.serialise_game(player='a'), expected_log)
        expected_log = "a:?\nb:1\nc:?\nd:?\na:?\na,5,c,\nc-8"
        self.assertEqual(game.serialise_game(player='b'), expected_log)
        expected_log = "a:?\nb:?\nc:8\nd:?\na:?\na,5,c,\nc-8"
        self.assertEqual(game.serialise_game(player='c'), expected_log)
        expected_log = "a:?\nb:?\nc:?\nd:1\na:?\na,5,c,\nc-8"
        self.assertEqual(game.serialise_game(player='d'), expected_log)


class SelfConsistency(unittest.TestCase):
    """ In this test class we simply run several iterations of the game and
        we should get no exceptions being raised for illegal moves because
        we should only be choosing from those we are given.
        We also check that the game can loaded from a log and you get the same
        result as before you serialised the game.
    """
    def play_test_game(self, limit=100):
        players = ['a', 'b', 'c', 'd']
        game = Game(players)
        for _ in range(limit):
            if game.is_game_finished():
                break
            pmoves_one, pmoves_two = game.available_moves()
            possible_moves = pmoves_one.moves + pmoves_two.moves
            game.play_move(random.choice(possible_moves))
        return game

    def test_game(self):
        for _ in range(100):
            self.play_test_game()

    def test_load(self):
        for _ in range(100):
            # Note that the initial deal is not actually counted in the
            # limit of the moves so some games will have a high enough limit
            # to finish the game. There would be some that did anyway on
            # account of finishing through all but one player being out.
            limit = random.choice(range(len(card_pack)))
            game_one = self.play_test_game(limit=limit)
            log = game_one.serialise_game()
            players = ['a', 'b', 'c', 'd']
            try:
                game_two = Game(players, log=log)
            except Exception as e:
                print(log)
                raise e
            self.assertEqual(game_one.players, game_two.players)
            self.assertEqual(game_one.hands, game_two.hands)
            self.assertEqual(game_one.winners, game_two.winners)

if __name__ == "__main__":
    application.run(debug=True)
