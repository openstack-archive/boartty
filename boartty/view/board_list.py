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
from boartty.view import board as view_board
from boartty.view import mouse_scroll_decorator

ACTIVE_COL_WIDTH = 7

class BoardRow(urwid.Button):
    board_focus_map = {None: 'focused',
                         'active-project': 'focused-active-project',
                         'subscribed-project': 'focused-subscribed-project',
                         'unsubscribed-project': 'focused-unsubscribed-project',
                         'marked-project': 'focused-marked-project',
    }

    def selectable(self):
        return True

    def _setTitle(self, title, indent):
        self.board_title = title
        title = indent+title
        if self.mark:
            title = '%'+title
        else:
            title = ' '+title
        self.title.set_text(title)

    def __init__(self, app, board, topic, callback=None):
        super(BoardRow, self).__init__('', on_press=callback,
                                         user_data=(board.key, board.title))
        self.app = app
        self.mark = False
        self._style = None
        self.board_key = board.key
        if topic:
            self.topic_key = topic.key
            self.indent = '  '
        else:
            self.topic_key = None
            self.indent = ''
        self.board_title = board.title
        self.title = mywid.SearchableText('')
        self._setTitle(board.title, self.indent)
        self.title.set_wrap_mode('clip')
        self.active_stories = urwid.Text(u'', align=urwid.RIGHT)
        col = urwid.Columns([
                self.title,
                ('fixed', ACTIVE_COL_WIDTH, self.active_stories),
                ])
        self.row_style = urwid.AttrMap(col, '')
        self._w = urwid.AttrMap(self.row_style, None, focus_map=self.board_focus_map)
        self.update(board)

    def search(self, search, attribute):
        return self.title.search(search, attribute)

    def update(self, board):
        if board.subscribed:
            style = 'subscribed-project'
        else:
            style = 'unsubscribed-project'
        self._style = style
        if self.mark:
            style = 'marked-project'
        self.row_style.set_attr_map({None: style})
        #self.active_stories.set_text('%i ' % cache['active_stories'])

    def toggleMark(self):
        self.mark = not self.mark
        if self.mark:
            style = 'marked-project'
        else:
            style = self._style
        self.row_style.set_attr_map({None: style})
        self._setTitle(self.board_title, self.indent)

class BoardListHeader(urwid.WidgetWrap):
    def __init__(self):
        cols = [urwid.Text(u' Board'),
                (ACTIVE_COL_WIDTH, urwid.Text(u'Active'))]
        super(BoardListHeader, self).__init__(urwid.Columns(cols))

@mouse_scroll_decorator.ScrollByWheel
class BoardListView(urwid.WidgetWrap, mywid.Searchable):
    def getCommands(self):
        return [
            (keymap.TOGGLE_LIST_SUBSCRIBED,
             "Toggle whether only subscribed boards or all boards are listed"),
            (keymap.TOGGLE_LIST_ACTIVE,
             "Toggle listing of boards with active changes"),
            (keymap.TOGGLE_SUBSCRIBED,
             "Toggle the subscription flag for the selected board"),
            (keymap.REFRESH,
             "Sync subscribed boards"),
            (keymap.TOGGLE_MARK,
             "Toggle the process mark for the selected board"),
            (keymap.INTERACTIVE_SEARCH,
             "Interactive search"),
        ]

    def help(self):
        key = self.app.config.keymap.formatKeys
        commands = self.getCommands()
        return [(c[0], key(c[0]), c[1]) for c in commands]

    def __init__(self, app):
        super(BoardListView, self).__init__(urwid.Pile([]))
        self.log = logging.getLogger('boartty.view.board_list')
        self.searchInit()
        self.app = app
        self.active = True
        self.subscribed = False #True
        self.board_rows = {}
        self.listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.header = BoardListHeader()
        self.refresh()
        self._w.contents.append((app.header, ('pack', 1)))
        self._w.contents.append((urwid.Divider(),('pack', 1)))
        self._w.contents.append((urwid.AttrWrap(self.header, 'table-header'), ('pack', 1)))
        self._w.contents.append((self.listbox, ('weight', 1)))
        self._w.set_focus(3)

    def interested(self, event):
        if not (isinstance(event, sync.BoardAddedEvent)
                or
                isinstance(event, sync.StoryAddedEvent)
                or
                (isinstance(event, sync.StoryUpdatedEvent) and
                 event.status_changed)):
            self.log.debug("Ignoring refresh board list due to event %s" % (event,))
            return False
        self.log.debug("Refreshing board list due to event %s" % (event,))
        return True

    def advance(self):
        pos = self.listbox.focus_position
        if pos < len(self.listbox.body)-1:
            pos += 1
            self.listbox.focus_position = pos

    def _deleteRow(self, row):
        if row in self.listbox.body:
            self.listbox.body.remove(row)
        if isinstance(row, BoardRow):
            del self.board_rows[(row.topic_key, row.board_key)]
        else:
            del self.topic_rows[row.topic_key]

    def _boardRow(self, i, board, topic):
        # Ensure that the row at i is the given board.  If the row
        # already exists somewhere in the list, delete all rows
        # between i and the row and then update the row.  If the row
        # does not exist, insert the row at position i.
        topic_key = topic and topic.key or None
        key = (topic_key, board.key)
        row = self.board_rows.get(key)
        while row:  # This is "if row: while True:".
            if i >= len(self.listbox.body):
                break
            current_row = self.listbox.body[i]
            if (isinstance(current_row, BoardRow) and
                current_row.board_key == board.key):
                break
            self._deleteRow(current_row)
        if not row:
            row = BoardRow(self.app, board, topic, self.onSelect)
            self.listbox.body.insert(i, row)
            self.board_rows[key] = row
        else:
            row.update(board)
        return i+1

    def refresh(self):
        if self.subscribed:
            self.title = u'Subscribed boards'
            self.short_title = self.title[:]
            if self.active:
                self.title += u' with active stories'
        else:
            self.title = u'All boards'
            self.short_title = self.title[:]
        self.app.status.update(title=self.title)
        with self.app.db.getSession() as session:
            i = 0
            for board in session.getBoards(subscribed=self.subscribed):
                #self.log.debug("board: %s" % board.name)
                i = self._boardRow(i, board, None)
        while i < len(self.listbox.body):
            current_row = self.listbox.body[i]
            self._deleteRow(current_row)

    def toggleSubscribed(self, board_key):
        with self.app.db.getSession() as session:
            board = session.getBoard(board_key)
            board.subscribed = not board.subscribed
            ret = board.subscribed
        return ret

    def onSelect(self, button, data):
        board_key, board_name = data
        self.app.changeScreen(view_board.BoardView(self.app, board_key))

    def toggleMark(self):
        if not len(self.listbox.body):
            return
        pos = self.listbox.focus_position
        row = self.listbox.body[pos]
        row.toggleMark()
        self.advance()

    def getSelectedRows(self, cls):
        ret = []
        for row in self.listbox.body:
            if isinstance(row, cls) and row.mark:
                ret.append(row)
        if ret:
            return ret
        pos = self.listbox.focus_position
        row = self.listbox.body[pos]
        if isinstance(row, cls):
            return [row]
        return []

    def toggleSubscribed(self):
        rows = self.getSelectedRows(BoardRow)
        if not rows:
            return
        keys = [row.board_key for row in rows]
        subscribed_keys = []
        with self.app.db.getSession() as session:
            for key in keys:
                board = session.getBoard(key)
                board.subscribed = not board.subscribed
                if board.subscribed:
                    subscribed_keys.append(key)
        for row in rows:
            if row.mark:
                row.toggleMark()
        for key in subscribed_keys:
            self.app.sync.submitTask(sync.SyncBoardTask(key))
        self.refresh()

    def keypress(self, size, key):
        if self.searchKeypress(size, key):
            return None

        if not self.app.input_buffer:
            key = super(BoardListView, self).keypress(size, key)
        keys = self.app.input_buffer + [key]
        commands = self.app.config.keymap.getCommands(keys)
        ret = self.handleCommands(commands)
        if ret is True:
            if keymap.FURTHER_INPUT not in commands:
                self.app.clearInputBuffer()
            return None
        return key

    def handleCommands(self, commands):
        if keymap.TOGGLE_LIST_ACTIVE in commands:
            self.active = not self.active
            self.refresh()
            return True
        if keymap.TOGGLE_LIST_SUBSCRIBED in commands:
            self.subscribed = not self.subscribed
            self.refresh()
            return True
        if keymap.TOGGLE_SUBSCRIBED in commands:
            self.toggleSubscribed()
            return True
        if keymap.TOGGLE_MARK in commands:
            self.toggleMark()
            return True
        if keymap.REFRESH in commands:
            self.app.sync.submitTask(
                sync.SyncSubscribedBoardsTask(sync.HIGH_PRIORITY))
            self.app.status.update()
            self.refresh()
            return True
        if keymap.INTERACTIVE_SEARCH in commands:
            self.searchStart()
            return True
        return False
