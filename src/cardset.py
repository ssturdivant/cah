from __future__ import print_function

import glob
import os
import yaml

from twisted.python import log

def num_white_cards(text):
    return max(1, text.count("{}"))

def enumerate_cards(cards):
    for ident, card in enumerate(cards):
        card["card_id"] = ident

class Cardset(object):
    def __init__(self, data_path):
        self.data_path = data_path
        self.active_files = []
        self.black_cards = []
        self.white_cards = []
        self.refresh_files()
        #TODO selector
        self.active_files = self.available_files

    def refresh_files(self):
        self.available_files = glob.glob(os.path.join(self.data_path, "*.yml"))

    def refresh_cards(self):
        self.black_cards = []
        self.white_cards = []
        for filename in self.active_files:
            log.msg("Loading {}".format(filename))
            with open(filename) as f:
                cardset = yaml.load(f)
            log.msg("{} loaded".format(filename))
            for c in cardset["black"]:
                self.black_cards.append({
                    "tag": cardset["tag"],
                    "text": c,
                    "num_white_cards": num_white_cards(c),
                })
            for c in cardset["white"]:
                self.white_cards.append({
                    "tag": cardset["tag"],
                    "text": c,
                })
        enumerate_cards(self.black_cards)
        enumerate_cards(self.white_cards)
