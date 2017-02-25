# Copyright 2014 OpenStack Foundation
# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

import logging
import urwid

from boartty import keymap
from boartty import mywid
from boartty import sync
from boartty.view import mouse_scroll_decorator

# +-----listbox---+
# |table pile     |
# |               |
# |+------+-cols-+|
# ||+----+|+----+||
# |||    |||    |||
# |||pile|||pile|||
# |||    |||    |||
# ||+----+|+----+||
# |+------+------+|
# +---------------+

class LanePile(urwid.Pile):
    def __init__(self, lane):
        self.key = lane.key
        self.manager = mywid.ListUpdateManager(self)
            #self, LaneRow,
            #lambda x: (LaneRow(x), (urwid.widget.WEIGHT, 1)))
        super(LanePile, self).__init__([])

    def update(self, lane):
        pass #self.title.set_text(lane.worklist.title)

    def __eq__(self, other):
        if isinstance(other, LanePile):
            return self.key == other.key
        return False

class TitleRow(urwid.Text):
    def __init__(self, title):
        super(TitleRow, self).__init__(title)
        self.title = title

    def update(self, other):
        self.title = other.title
        self.set_text(self.title)

    def __eq__(self, other):
        if isinstance(other, TitleRow):
            return self.title == other.title
        return False

class LaneRow(mywid.TextButton):
    def __init__(self, item, board_view):
        super(LaneRow, self).__init__(item.title, on_press=self.open)
        self.key = item.key
        self.board_view = board_view
        self.title = item.title
        self.story_key = item.dereferenced_story_key

    def update(self, other):
        self.title = other.title
        self.story_key = other.story_key
        self.text.set_text(self.title)

    def __eq__(self, other):
        if isinstance(other, LaneRow):
            return self.key == other.key
        return False

    def open(self, *args):
        self.board_view.openItem(self.story_key)

class BoardView(urwid.WidgetWrap, mywid.Searchable):
    def getCommands(self):
        return [
            (keymap.REFRESH,
             "Sync current board"),
            (keymap.INTERACTIVE_SEARCH,
             "Interactive search"),
        ]

    def help(self):
        key = self.app.config.keymap.formatKeys
        commands = self.getCommands()
        return [(c[0], key(c[0]), c[1]) for c in commands]

    def interested(self, event):
        if not ((isinstance(event, sync.BoardUpdatedEvent) and
                 event.board_key == self.board_key) or
                (isinstance(event, sync.WorklistUpdatedEvent) and
                 event.worklist_key in self.worklist_keys)):
            self.log.debug("Ignoring refresh board due to event %s" % (event,))
            return False
        self.log.debug("Refreshing board due to event %s" % (event,))
        return True

    def __init__(self, app, board_key):
        super(BoardView, self).__init__(urwid.Pile([]))
        self.log = logging.getLogger('boartty.view.board')
        self.searchInit()
        self.app = app
        self.board_key = board_key
        self.worklist_keys = set()

        self.title_label = urwid.Text(u'', wrap='clip')
        self.description_label = urwid.Text(u'')
        board_info = []
        board_info_map={'story-data': 'focused-story-data'}
        for l, v in [("Title", self.title_label),
                     ("Description", self.description_label),
                     ]:
            row = urwid.Columns([(12, urwid.Text(('story-header', l), wrap='clip')), v])
            board_info.append(row)
        board_info = urwid.Pile(board_info)

        self.listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self._w.contents.append((self.app.header, ('pack', 1)))
        self._w.contents.append((urwid.Divider(), ('pack', 1)))
        self._w.contents.append((self.listbox, ('weight', 1)))
        self._w.set_focus(2)

        self.listbox.body.append(board_info)
        self.listbox.body.append(urwid.Divider())
        self.listbox_board_start = len(self.listbox.body)

        lane_columns = urwid.Columns([], dividechars=1)
        self.listbox.body.append(lane_columns)

        self.lane_manager = mywid.ListUpdateManager(lane_columns)

        self.refresh()
        self.listbox.set_focus(1)

    def refresh(self):
        with self.app.db.getSession() as session:
            board = session.getBoard(self.board_key)
            self.log.debug("Display board %s", board)
            self.title = board.title
            self.app.status.update(title=self.title)
            self.title_label.set_text(('story-data', board.title))
            self.description_label.set_text(('story-data', board.description))
            lanes = [
                (LanePile(x), (urwid.widget.WEIGHT, 1, False))
                for x in board.lanes
            ]
            self.lane_manager.update(lanes)
            for i, lane in enumerate(board.lanes):
                lane_pile = self.lane_manager.widget.contents[i][0]
                items = [
                    (TitleRow(lane.worklist.title), (urwid.widget.WEIGHT, 1))
                ]
                for item in lane.worklist.items:
                    items.append((TitleRow(u''), (urwid.widget.WEIGHT, 1)))
                    items.append((LaneRow(item, self), (urwid.widget.WEIGHT, 1)))
                lane_pile.manager.update(items)

    def openItem(self, story_key):
        self.log.debug("Open story %s", story_key)
        self.app.openStory(story_key)

    def keypress(self, size, key):
        if self.searchKeypress(size, key):
            return None

        if not self.app.input_buffer:
            key = super(BoardView, self).keypress(size, key)
        keys = self.app.input_buffer + [key]
        commands = self.app.config.keymap.getCommands(keys)
        ret = self.handleCommands(commands)
        if ret is True:
            if keymap.FURTHER_INPUT not in commands:
                self.app.clearInputBuffer()
            return None
        return key

    def handleCommands(self, commands):
        if keymap.REFRESH in commands:
            self.app.sync.submitTask(
                sync.SyncBoardTask(self.board_key, sync.HIGH_PRIORITY))
            self.app.status.update()
            self.refresh()
            return True
        if keymap.INTERACTIVE_SEARCH in commands:
            self.searchStart()
            return True
        return False
