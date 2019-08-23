"""
Go/no-go task, demo for NCB
"""



import datetime
import itertools
import tables
import threading
from random import random


from rpilot.core import hardware
from rpilot.tasks import Task
from rpilot.stim.visual.visuals import Grating, Grating_Continuous
from collections import OrderedDict as odict
from rpilot.core.networking import Net_Node

from rpilot import prefs
TASK = 'GoNoGo'

class GoNoGo(Task):
    STAGE_NAMES = ["request", "discrim", "reinforcement"]

    # Class attributes

    # List of needed params, returned data and data format.
    # Params are [name]={'tag': Human Readable Tag, 'type': 'int', 'float', 'check', etc.}
    PARAMS = odict()
    PARAMS['reward'] = {'tag': 'Reward Duration (ms)',
                        'type': 'int'}
    PARAMS['timeout']        = {'tag':'Delay Timeout (ms)',
                                'type':'int'}
    PARAMS['stim'] = {'tag':  'Visuals',
                      'type': 'visuals'}

    # Set plot params, which data should be plotted, its default shape, etc.
    PLOT = {
        'data': {
            'x': 'shaded',
            'target': 'point',
            'response': 'segment'
        },
        'continuous': True
    }

    # PyTables Data descriptor
    # for numpy data types see http://docs.scipy.org/doc/numpy/reference/arrays.dtypes.html#arrays-dtypes-constructing
    class TrialData(tables.IsDescription):
        # This class allows the Mouse object to make a data table with the correct data types. You must update it for any new data you'd like to store
        trial_num = tables.Int32Col()
        target = tables.BoolCol()
        response = tables.StringCol(1)
        correct  = tables.Int32Col()
        RQ_timestamp = tables.StringCol(26)
        DC_timestamp = tables.StringCol(26)
        shift = tables.Float32Col()
        angle = tables.Float32Col()
        delay = tables.Float32Col()

    HARDWARE = {
        'POKES': {
            'C': hardware.Beambreak,
        },
        'LEDS': {
            'C': hardware.LED_RGB,
        },
        'PORTS': {
            'C': hardware.Solenoid,
        },
        'FLAGS': {
            'F': hardware.Flag
        }
    }

    CHILDREN = {
        'WHEEL': {
            'task_type': "Wheel Child",
        }
    }

    def __init__(self, stim=None, reward = 50, timeout = 1000, stage_block = None,**kwargs):
        super(GoNoGo, self).__init__()

        self.stage_block = stage_block
        self.trial_counter = itertools.count()

        self.punish_dur = 500.0

        self.reward = reward
        self.timeout = timeout

        self.init_hardware()
        self.set_reward(self.reward)

        self.node = Net_Node(id="T_{}".format(prefs.NAME),
                             upstream=prefs.NAME,
                             port=prefs.MSGPORT,
                             listens={},
                             instance=True)

        # get our child started
        self.mouse = kwargs['mouse']
        value = {
            'child': {'parent': prefs.NAME, 'mouse': kwargs['mouse']},
            'task_type': 'Wheel Child',
            'mouse': kwargs['mouse']
        }

        self.node.send(to=prefs.NAME, key='CHILD', value=value)

        # hardcoding stimulus for testing
        self.stim = Grating(angle=0, freq=(4,0), rate=1, size=(4,4))

        self.stages = itertools.cycle([self.request, self.discrim, self.reinforce])


    def request(self):
        # wait for the mouse to hold the wheel still
        # Set the event lock
        self.stage_block.clear()
        self.punish_block.wait()

        # Reset all the variables that need to be
        #for v in self.resetting_variables:
        #    v = None

        # reset triggers if there are any left
        self.triggers = {}

        # calculate orientation change
        # half the time, don't change, otherwise, do change

        if random() < 0.5:
            self.shift = 0
            self.target = False
        else:
            self.shift = random()*180.0
            self.target = True



        # Set sound trigger and LEDs
        # We make two triggers to play the sound and change the light color
        change_to_blue = lambda: self.pins['LEDS']['C'].set_color([0, 0, 255])

        # set triggers
        self.triggers['F'] = [change_to_blue, lambda: self.stim.play('shift', self.shift )]

        # set to green in the meantime
        self.set_leds({'C': [0, 255, 0]})

        # tell our wheel to start measuring
        self.node.send(to=[prefs.NAME, prefs.CHILDID, 'wheel_0'],
                       key="MEASURE",
                       value={'mode':'steady',
                              'thresh':100})

        self.current_trial = self.trial_counter.next()
        data = {
            'target': self.target,
            'shift': self.shift,
            'trial_num': self.current_trial
        }

        self.current_stage = 0
        return data

    def discrim(self):
        self.stage_block.clear()

        # if the mouse licks on a good trial, reward.
        # set a trigger to respond false if delay time elapses
        if self.target:
            self.triggers['C'] = [lambda: self.respond(True), self.pins['PORTS']['C'].open]
            self.triggers['T'] = [lambda: self.respond(False), self.punish]
        # otherwise punish
        else:
            self.triggers['C'] = [lambda: self.respond(True), self.punish]
            self.triggers['T'] = [lambda: self.respond(False), self.pins['PORTS']['C'].open]

        # the stimulus has just started playing, wait a bit and then shift it (if we're gonna
        # choose a random delay
        delay = 0.0
        if self.shift != 0:
            delay = (random()*3000.0)+1000.0
            self.delayed_set(delay, 'shift', self.shift)

        self.timer = threading.Timer(5.0, self.handle_trigger, args=('T', True, None)).start()

        data = {
            'delay': delay,
            'RQ_timestamp': datetime.datetime.now().isoformat(),
            'trial_num': self.current_trial
        }


        return data





    def reinforce(self):
        # don't clear stage block here to quickly move on
        if self.response == self.target:
            self.correct = 1
        else:
            self.correct = 0

        self.set_leds({'C': [0, 0, 0]})
        # stop timer if it's still going
        try:
            self.timer.cancel()
        except AttributeError:
            pass
        self.timer = None

        data = {
            'DC_timestamp': datetime.datetime.now().isoformat(),
            'response': self.response,
            'correct': self.correct,
            'trial_num': self.current_trial,
            'TRIAL_END': True
        }
        return data

    def respond(self, response):
        self.response = response

    def delayed_set(self, delay, attr, val):
        threading.Timer(float(delay)/1000.0, self._delayed_shift, args=(attr,val)).start()

    def _delayed_shift(self, attr, val):
        self.stim.q.put(('shift', val))

    def punish(self):
        """
        Flash lights, play punishment sound if set
        """
        # TODO: If we're not in the last stage (eg. we were timed out after stim presentation), reset stages
        self.punish_block.clear()

        if self.punish_stim:
            self.stim_manager.play_punishment()

        # self.set_leds()
        self.flash_leds()
        threading.Timer(self.punish_dur / 1000., self.punish_block.set).start()

