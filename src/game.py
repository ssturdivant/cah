from itertools import cycle, islice
import os
import random
from threading import Timer
import copy

import yaml
from twisted.python import log

from utils import roundrobin, frozendict
from cardset import Cardset

ABS_PATH = os.path.dirname(os.path.realpath(__file__))

publish = "http://{}/ws/{}#{}"

class Game(object):
    def __init__(self, game_id, empty_game_callback):
        self.users = []
        self.game_id = game_id
        self._empty_game_callback = empty_game_callback

        self.cardset = Cardset(os.path.join(ABS_PATH, "data"))
        self.cardset.refresh_cards()

        self._state = State()

    _wamp_server = None

    @staticmethod
    def register_cah_wamp_client(client):
        Game._wamp_server = client

    _publish_uri = ""

    @staticmethod
    def set_publish_uri(publish_uri):
        Game._publish_uri = publish_uri

    def add_user(self, username, session):
        if self._get_user(username):
            return False

        self.users.append(User(username, session))
        self.sync_users()
        return True

    def remove_user(self, username):
        try:
            user = self._get_user(username)
            if not user:
                return
            if user.czar:
                try:
                    if self._state.step == "start_round":
                        self._start_round()
                    elif self._state.step == "begin_judging":
                        self._force_round_end()
                    elif self._state.step == "round_winner":
                        self._set_next_czar()
                except:
                    pass
                self.users.remove(user)
            else:
                self.users.remove(user)

            if len([u for u in self.users if not u.afk]) < 3:
                self._cancel_round_timer()
                self._set_step("no_game")
                self.sync_me()

        except ValueError:
            pass
        if len(self.users) == 0:
            self._empty_game_callback(self.game_id)
        self.sync_users()

    def sync_users(self):
        users = []
        black_card = self._state.black_card
        for user in self.users:
            if self._state.step == "start_round" and user.is_unplayed(
                black_card['num_white_cards']):
                user.unplayed = True
            else:
                user.unplayed = False
            users.append(user)

        self._publish("sync_users", {"users": [x.to_dict() for x in users]})

    def start_game(self):
        if len([u for u in self.users if not u.afk]) < 3:
            return "Can't start a game with less than 3 users"
        try:
            self._state.round_timer.cancel()
        except:
            pass
        self._state = State(self.cardset.black_cards, self.cardset.white_cards)
        for user in self.users:
            user.reset()
        self._start_round()

    def choose_white(self, username, card_id):
        user = self._get_user(username)
        max_whites = self._state.black_card['num_white_cards']

        card = next((x for x in user.hand if x['card_id'] == int(card_id)), None)
        if card is None:
            # The user has managed to play a card not in their hand; force sync
            self._publish("send_hand",
                {"white_cards": user.hand},
                eligible=[user.session])
            return

        whites_played = len(user.white_cards_played) + 1
        if whites_played > max_whites:
            raise ValueError("[](/flutno)")
        if whites_played == max_whites:
            self._publish("max_whites",
                eligible=[self._get_user(username).session])

        user.hand.remove(card)
        user.white_cards_played.append(card)
        user.afk = False

        self.sync_users()
        self._publish("white_chosen",
            exclude=[self._get_user(username).session])
        self._update_round()

    def judge_group(self, username, group_id):
        czar = self._get_user(username)
        if (not czar.czar) or self._state.step != "begin_judging":
            raise ValueError('[](/abno)')

        self._cancel_round_timer()
        self._set_step("judge_group")
        round_winner = self._get_user(session_id=group_id)
        round_winner.score += 1
        round_winner.round_winner = True

        self._set_step("round_winner")

        black_text = self._state.black_card['text'];
        white_cards_text = [x['text'] for x in round_winner.white_cards_played]

        message =  self._get_round_winner_message(black_text, white_cards_text)
        self._publish("round_winner", {
            "username": round_winner.username,
            "group_id": round_winner.session.session_id,
            "message_parts": message
        })

        if round_winner.score >= self._state.winning_score:
            self._publish("winner", round_winner.username)
            self._set_step("no_game")
            self.sync_me()
        else:
            self.sync_users()
            self._publish('show_timer', {
                "title": "Next Round",
                "duration": 10
            })
            Timer(10, self._start_round, ()).start()

    def sync_me(self):
        self.sync_users()
        self._publish("sync_me", {
            "game_running": False if self._state.step == "no_game" else True
        })

    def update_afk(self, username, afk):
        self._get_user(username).afk = afk
        self._update_round()
        self.sync_users()

    def restart_timer(self):
        self._start_round_timer(self._state.round_length)

    def _start_round_timer(self, duration):
        self._cancel_round_timer()
        self._publish("show_timer", {
            "title": "Round ending in: ",
            "duration": self._state.round_length
        })
        self._state.round_timer = Timer(duration,
            self._force_round_end, ())
        self._state.round_timer.start()

    def _cancel_round_timer(self):
        try:
            self._state.round_timer.cancel()
        except:
            pass
        self._publish("cancel_timer")

    def _get_round_winner_message(self, black_text, white_cards_text):
        def format_cards(cards_iter, class_iter):
            message_parts = list(cards_iter)
            if message_parts[-1] == '.':
                message_parts = message_parts[:-1]
            last = len(message_parts) - 1
            return [{
                        "class": class_iter.next(),
                        "text": x.rstrip('.') if i < last else x
                    } for i, x in enumerate(message_parts)]

        if not "{}" in black_text:
            css_class = cycle(["black", "white"])
            white_cards_text[0] = ' ' + white_cards_text[0]
            return format_cards(roundrobin([black_text], white_cards_text), css_class)
        elif black_text.startswith("{}"):
            black_parts = black_text.split("{}")
            black_parts.pop(0)
            css_class = cycle(["white", "black"])
            return format_cards(roundrobin(white_cards_text, black_parts), css_class)
        else:
            black_parts = black_text.split("{}")
            css_class = cycle(["black", "white"])
            return format_cards(roundrobin(black_parts, white_cards_text), css_class)

    def _start_round(self):
        self._set_step("start_round")
        self._publish("start_round")
        for user in self.users:
            user.white_cards_played = []
            user.round_winner = False
            if user.playing_round is None:
                user.playing_round = True

        black_card = self._get_black_card()
        self._state.black_card = black_card

        self._publish("add_black", black_card)
        czar = self._set_next_czar()
        self._publish("czar_chosen", czar.username)
        self.sync_users()

        if black_card['num_white_cards'] >= 3:
            extra_cards = black_card['num_white_cards'] - 1
        else:
            extra_cards = 0

        for user in self.users:
            if not user.czar and not user.afk:
                num_cards = len(user.hand)
                cards = self._get_white_cards(10 + extra_cards - num_cards)
                if len(cards) > 0:
                    user.hand.extend(cards)
                    self._publish("send_hand",
                        {"white_cards": user.hand},
                        eligible=[user.session])
        self._start_round_timer(self._state.round_length)

    def _set_next_czar(self):
        czar_idx = next((idx for (idx, u) in enumerate(self.users) if u.czar), -1)
        for user in self.users:
            user.czar = False
        next_czar = next(u for u in islice(cycle(self.users), czar_idx+1, len(self.users)+czar_idx+1) if not u.afk)
        next_czar.czar = True
        return next_czar

    def _get_white_cards(self, num_cards):
        # If the deck is about to run out, draw up the rest of the deck and reshuffle
        rest_draw = []
        if num_cards >= len(self._state.available_white_cards):
            rest_draw = self._state.available_white_cards
            num_cards -= len(self._state.available_white_cards)
            self._state.available_white_cards = set(copy.deepcopy(self._white_cards))
            # Remove cards currently accounted for elsewhere
            self._state.available_white_cards -= rest_draw
            for user in self.users:
                self._state.available_white_cards -= set(user.hand)

	# Reseed the RNG before we use it! Otherwise the system clock will be used to seed when the generator is initialized; which is probably once and certainly not enough.
	random.seed(os.urandom(64));
	
        # This is not robust if the game is configured with very large hands or very few white cards
        cards = random.sample(self._state.available_white_cards, num_cards)
        self._state.available_white_cards -= set(cards)
        cards.extend(rest_draw)
        return cards

    def _get_black_card(self):
        if len(self._state.available_black_cards) <= 0:
            self._state.avalable_black_cards = set(copy.deepcopy(self._black_cards))
	random.seed(os.urandom(64));
        card = random.sample(self._state.available_black_cards, 1)[0]
        self._state.available_black_cards.remove(card)
        return card

    def _update_round(self):
        # Playing white cards, see if round should go to judging
        if self._state.step == "start_round":
            players_outstanding = False
            max_whites = self._state.black_card['num_white_cards']
            for user in self.users:
                if user.czar or user.afk or not user.playing_round:
                    continue
                if len(user.white_cards_played) != max_whites:
                    players_outstanding = True

            if not players_outstanding:
                self._cancel_round_timer()
                cards = []
                for user in self.users:
                    if user.czar or user.afk:
                        continue
                    cards.append({
                        "group_id": user.session.session_id,
                        "white_cards": user.white_cards_played,
                        "num_cards": max_whites
                    })
                self._set_step("begin_judging")
                random.shuffle(cards)
                self._publish("begin_judging", {"cards": cards})
                self.sync_users()
                self._start_round_timer(self._state.round_length)

    def _set_step(self, step):
        log.msg("Setting step to: {0}".format(step))
        self._state.step = step

    def _get_user(self, username=None, session_id=None):
        if username:
            return next((u for u in self.users if u.username == username), None)
        if session_id:
            return next((u for u in self.users if u.session.session_id == session_id), None)


    def _publish(self, topic, data=None, exclude=None, eligible=None):
        if not exclude:
            exclude = []
        log.msg("URI: {}".format(Game._publish_uri))
        topic = publish.format(Game._publish_uri, self.game_id, topic)
        log.msg(
            "Publishing: {0}, Data: {1}, exclude: {2}, eligible: {3}".format(
                topic, data, exclude, eligible))
        if Game._wamp_server:
            Game._wamp_server.dispatch(topic,
                data, exclude=exclude, eligible=eligible)


    def _force_round_end(self, set_afk=True):
        if self._state.step == "start_round":
            max_whites = self._state.black_card['num_white_cards']
            for user in self.users:
                if user.czar or user.afk or not user.playing_round:
                    continue
                if len(user.white_cards_played) != max_whites:
                    if set_afk:
                        user.afk = True
                    user.white_cards_played = []
            self._update_round()
        elif self._state.step == "begin_judging":
            for user in self.users:
                if user.czar:
                    self._start_round()
                    user.afk = True
                    user.czar = None
                    break


class User(object):
    def __init__(self, username, session):
        self.username = username
        self.white_cards_played = []
        self.hand = []
        self.czar = False
        self.played_round = ''
        self.score = 0
        self.playing_round = None
        self.afk = False
        self.unplayed = False
        self.round_winner = False
        self.session = session

    def to_dict(self):
        return {
            "username": self.username,
            "session_id": self.session.session_id,
            "czar": self.czar,
            "score": self.score,
            "afk": self.afk,
            "played_round": self.played_round,
            "unplayed": self.unplayed,
            "round_winner": self.round_winner
        }

    def reset(self):
        self.white_cards_played = []
        self.hand = []
        self.czar = False
        self.score = 0
        self.played_round = '',
        self.unplayed = False,
        self.round_winner = False

    def is_unplayed(self, max_whites):
        if self.czar or self.afk or not self.playing_round:
            return False
        played = len(self.white_cards_played)
        if played < max_whites:
            return True
        return False


class State(object):
    def __init__(self, black_cards=None, white_cards=None):
        self.step = "no_game"
        self.available_white_cards = []
        self.available_black_cards = []
        if white_cards:
            self.available_white_cards = set(frozendict(card) for card in white_cards)
        if black_cards:
            self.available_black_cards = set(frozendict(card) for card in black_cards)
        log.msg("Black cards: {}, white cards: {}".format(len(self.available_black_cards), len(self.available_white_cards)))
        self.winning_score = 6
        self.round_length = 90
        self.black_card = None
        self.round_timer = None
        self.extended_round_time = self.round_length
