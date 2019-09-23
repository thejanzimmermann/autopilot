"""
Sub-tasks that serve as children to other tasks
"""

from collections import OrderedDict as odict
from autopilot import prefs
from autopilot.core.hardware import Wheel
from itertools import cycle

class Wheel_Child(object):
    STAGE_NAMES = ['collect']

    PARAMS = odict()
    PARAMS['fs'] = {'tag': 'Velocity Reporting Rate (Hz)',
                    'type': 'int'}
    PARAMS['thresh'] = {'tag': 'Distance Threshold',
                        'type': 'int'}



    def __init__(self, stage_block=None, **kwargs):

        self.subject = Wheel(gpio_trig=True, pins=prefs.PINS['OUTPUT'],
                           mode="steady", thresh=100)
        self.stages = cycle([self.noop])

    def noop(self):
        # just fitting in with the task structure.
        return {}

    def end(self):
        self.subject.release()


