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
        self.refresh()

    def refresh(self):
        with self.app.db.getSession() as session:
            board = session.getBoard(self.board_key)
            self.log.debug("Display board %s", board)
            self.title = board.title
            self.app.status.update(title=self.title)
            self.title_label.set_text(('story-data', board.title))
            self.description_label.set_text(('story-data', board.description))
            columns = []
            for lane in board.lanes:
                items = []
                self.log.debug("Display lane %s", lane)
                items.append(urwid.Text(lane.worklist.title))
                self.worklist_keys.add(lane.worklist.key)
                for item in lane.worklist.items:
                    self.log.debug("Display item %s", item)
                    items.append(mywid.TextButton(item.title,
                                                  on_press=self.openItem,
                                                  user_data=item.dereferenced_story_key))
                pile = urwid.Pile(items)
                columns.append(pile)
            columns = urwid.Columns(columns)
            for x in self.listbox.body[self.listbox_board_start:]:
                self.listbox.body.remove(x)
            self.listbox.body.append(columns)

    def openItem(self, widget, story_key):
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
