#! /usr/bin/python
import random
import itertools
import time
import socket

DIE_SIZE = 6
NUM_DICE = 6
GOAL = 10000

class Player:
    def __init__(self, name):
        self.name = name

    def __str__(self): return self.name

class RerollWithTwo(Player):
    def move(self, roll):
        return roll.trim() if len(roll.toArray()) >= 2 else None

class RerollWithFour(Player):
    def move(self, roll):
        return roll.trim() if len(roll.toArray()) >= 4 else None

class RerollWithThree(Player):
    def move(self, roll):
        return roll.trim() if len(roll.toArray()) >= 3 else None

class TakeOnlyOnesAndRerollWithThree(Player):
    def move(self, roll):
        if len(roll.toArray()) >= 3:
            Roll(dice=list(itertools.repeat(1, roll.toArray().count(1))))
        else:
            return roll.trim()

class HumanPlayer(Player):
    def move(self, roll):
        prompt = ("{}, input values to keep, separated by spaces: "
                  .format(self.name))
        response = input(prompt)
        keepers = Roll(dice=list(int(n) for n in response.split()))
        while not (keepers.isSubsetOf(roll) and keepers.isTrimmed()):
            response = input("{} is not a scoreable subset of {}. Try again: "
                             .format(keepers, roll))
            keepers = Roll(dice=[int(n) for n in response.split()])
        return keepers if keepers.toArray() else None
        return None if keepers.score() == 0 else keepers

class RemotePlayer(Player):

    def __init__(self, name, host, port):
        self.name = name
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((host, port))
        print("{} connected successfully.".format(self.name))
        
    def sendMessage(self, msg, encoding='UTF-8'):
        self.conn.send("\2{}\3{}".format(len(msg), msg).encode(encoding))

    def recvMessage(self):
        return str(self.conn.recv(1024))[2:-1]
        
    def move(self, roll):
        self.sendMessage(str(roll))
        response = self.recvMessage()
        while response == "NOP": response = self.recvMessage()

        if response == "\n":
            reroll = None
        else:
            try:
                reroll = Roll(dice=[int(n) for n in response.split()])
            except ValueError:
                reroll = None

        return reroll if ((reroll is not None) and
                          reroll.isSubsetOf(roll)) else None

class Roll:

    def __init__(self, numDice=6, dice=None):
        if dice is not None:
            self.dice = dice
        else:
            self.dice = [random.randint(1, DIE_SIZE)
                          for _ in range(numDice)]

    def __str__(self):
        return str(self.dice)

    def toArray(self):
        return self.dice.copy()

    def isSubsetOf(self, roll):
        otherDice = roll.toArray()
        for d in self.dice:
            if not d in otherDice:
                return False
            else:
                otherDice.remove(d)
        else:
            return True

    def trim(self):
        """Return a new roll with non-scoring dice ommited."""
        newDice = self.dice.copy()
        for n in [2, 3, 4, 6]:
            while newDice.count(n) % 3: 
                newDice.remove(n)
        return Roll(dice=newDice)
        
    def score(self):
        score = 0
        for k, g in itertools.groupby(sorted(self.dice)):
            reps = len(list(g))
            if k == 1:
                score += 1000 * (reps // 3) + 100 * (reps % 3)
            elif k == 5:
                score += 500 * (reps // 3) + 50 * (reps % 3)
            else:
                score += k*100 * (reps // 3)
        return score

    def isTrimmed(self):
        """Every die in this roll is necessary for the total score."""
        for k, g in itertools.groupby(sorted(self.dice)):
            reps = len(list(g))
            if self.dice and not (k == 1 or k == 5 or reps % 3 == 0):
                return False
        else:
            return True

class Game:

    def __init__(self, *plyrs):
        self.plyrs = plyrs
        self.remotePlyrs = []
        self.gameLog = ""
        for p in plyrs:
            # All remote players are expected to have a conn attribute
            if "conn" in dir(p):
                self.remotePlyrs.append(p)
        scores = dict()
        for plyr in plyrs:
            scores[plyr.name] = 0
        self.scores = scores
        self.quickRun = False

    def gameMsg(self, msg):
        for plyr in self.remotePlyrs:
            plyr.sendMessage(msg)
        self.gameLog += (msg + "\n")
        if not self.quickRun: print(msg)

    def quickRun(self):
        self.quickRun = True
        self.play()

    def play(self):
        endgameCounter = 0
        turnCounter = 0
        for plyr in itertools.cycle(self.plyrs):
            self.turn(plyr)
            turnCounter += 1

            if self.scores[plyr.name] > GOAL or endgameCounter > 0:
                endgameCounter += 1

            if endgameCounter >= len(self.plyrs): # Game ends
                rounds = turnCounter // len(self.plyrs)
                self.gameMsg("Game complete in {} turns ({} rounds):\n"
                                 .format(turnCounter, rounds))
                def key(plyr): return -self.scores[plyr.name]
                for p in sorted(self.plyrs, key=key):
                    self.gameMsg("{} scored {}"
                                     .format(p.name, self.scores[p.name]))
                return self.scores

    def turn(self, plyr):
        roll = Roll(NUM_DICE)
        self.gameMsg("{} rolls {}.".format(plyr.name, roll))
        turnscore = 0
        while True:
            if roll.score() == 0: # Player farkles
                self.gameMsg("{} farkles.".format(plyr.name))
                turnscore = 0
                break
            response = plyr.move(roll)
            if response is None: # Player scores dice
                self.gameMsg("{} ends turn, keeping {} ({} points)."
                                 .format(plyr.name, roll.trim(), roll.score()))
                turnscore += roll.score()
                break
            elif response.isTrimmed() and not response.score() == 0: # Player re-rolls
                self.gameMsg("{} keeps {} ({} points) and continues."
                      .format(plyr.name, response, response.score()))
                turnscore += response.score()
                numReroll = len(roll.toArray()) - len(response.toArray())
                roll = Roll(NUM_DICE if numReroll == 0 else numReroll)
                self.gameMsg("{} rolls {}.".format(plyr.name, roll))
            else: # In case of bad response, game automatically scores dice
                self.gameMsg("Bad response from {}: {}."
                             .format(plyr, response))
                self.gameMsg("{} ends turn, keeping {} ({} points)."
                                 .format(plyr.name, roll.trim(), roll.score()))
                turnscore += roll.score()
                break
        self.award(plyr, turnscore)
        
    def award(self, plyr, points):
        self.scores[plyr.name] += points
        self.gameMsg("{} scores {} points for a total of {}.\n"
                     .format(plyr.name, points, self.scores[plyr.name]))
        if not self.quickRun: time.sleep(.2)

if __name__ == '__main__':
    host = input("Remote player host ip adress (Or press ENTER to skip): ")
    if host: port = int(input("Remote player port: ")) or 6464
    name = input("Player name: ") or 'Player'
    
    player = (RemotePlayer(name, host, int(port)) if host
              else HumanPlayer(name))

    Game(TakeOnlyOnesAndRerollWithThree('Bot'), player).play()
