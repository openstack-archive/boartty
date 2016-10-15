# Copyright 2014 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

DEFAULT_PALETTE={
    'focused': ['default,standout', ''],
    'header': ['white,bold', 'dark blue'],
    'error': ['light red', 'dark blue'],
    'table-header': ['white,bold', ''],
    'link': ['dark blue', ''],
    'focused-link': ['light blue', ''],
    'footer': ['light gray', 'dark gray'],
    'search-result': ['default,standout', ''],
    # Story view
    'story-data': ['dark cyan', ''],
    'focused-story-data': ['light cyan', ''],
    'story-header': ['light blue', ''],
    'task-id': ['dark cyan', ''],
    'task-title': ['light green', ''],
    'task-project': ['light blue', ''],
    'task-status': ['yellow', ''],
    'task-assignee': ['light cyan', ''],
    'task-note': ['default', ''],
    'focused-task-id': ['dark cyan,standout', ''],
    'focused-task-title': ['light green,standout', ''],
    'focused-task-project': ['light blue,standout', ''],
    'focused-task-status': ['yellow,standout', ''],
    'focused-task-assignee': ['dark cyan,standout', ''],
    'focused-task-note': ['default', ''],
    'story-event-name': ['yellow', ''],
    'story-event-own-name': ['light cyan', ''],
    'story-event-header': ['brown', ''],
    'story-event-own-header': ['dark cyan', ''],
    'story-event-draft': ['dark red', ''],
    'story-event-button': ['dark magenta', ''],
    'focused-story-event-button': ['light magenta', ''],
    # project list
    'active-project': ['white', ''],
    'subscribed-project': ['default', ''],
    'unsubscribed-project': ['dark gray', ''],
    'marked-project': ['light cyan', ''],
    'focused-active-project': ['white,standout', ''],
    'focused-subscribed-project': ['default,standout', ''],
    'focused-unsubscribed-project': ['dark gray,standout', ''],
    'focused-marked-project': ['light cyan,standout', ''],
    # story list
    'active-story': ['default', ''],
    'inactive-story': ['dark gray', ''],
    'focused-active-story': ['default,standout', ''],
    'focused-inactive-story': ['dark gray,standout', ''],
    'starred-story': ['light cyan', ''],
    'focused-starred-story': ['light cyan,standout', ''],
    'held-story': ['light red', ''],
    'focused-held-story': ['light red,standout', ''],
    'marked-story': ['dark cyan', ''],
    'focused-marked-story': ['dark cyan,standout', ''],
    }

# A delta from the default palette
LIGHT_PALETTE = {
    'table-header': ['black,bold', ''],
    'active-project': ['black', ''],
    'subscribed-project': ['dark gray', ''],
    'unsubscribed-project': ['dark gray', ''],
    'focused-active-project': ['black,standout', ''],
    'focused-subscribed-project': ['dark gray,standout', ''],
    'focused-unsubscribed-project': ['dark gray,standout', ''],
    'story-data': ['dark blue,bold', ''],
    'focused-story-data': ['dark blue,standout', ''],
    'story-event-name': ['brown', ''],
    'story-event-own-name': ['dark blue,bold', ''],
    'story-event-header': ['black', ''],
    'story-event-own-header': ['black,bold', ''],
    'focused-link': ['dark blue,bold', ''],
    }

class Palette(object):
    def __init__(self, config):
        self.palette = {}
        self.palette.update(DEFAULT_PALETTE)
        self.update(config)

    def update(self, config):
        d = config.copy()
        if 'name' in d:
            del d['name']
        self.palette.update(d)

    def getPalette(self):
        ret = []
        for k,v in self.palette.items():
            ret.append(tuple([k]+v))
        return ret
