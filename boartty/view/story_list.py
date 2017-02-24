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

import datetime
import logging

import six
import urwid

from boartty import keymap
from boartty import mywid
from boartty import sync
from boartty.view import story as view_story
from boartty.view import mouse_scroll_decorator
import boartty.view


class ColumnInfo(object):
    def __init__(self, name, packing, value):
        self.name = name
        self.packing = packing
        self.value = value
        self.options = (packing, value)
        if packing == 'given':
            self.spacing = value + 1
        else:
            self.spacing = (value * 8) + 1


COLUMNS = [
    ColumnInfo('ID',      'given',   8),
    ColumnInfo('Title',   'weight',  4),
    ColumnInfo('Status',  'weight',  1),
    ColumnInfo('Creator', 'weight',  1),
    ColumnInfo('Updated', 'given',  10),
]


class StoryListColumns(object):
    def updateColumns(self):
        del self.columns.contents[:]
        cols = self.columns.contents
        options = self.columns.options

        for colinfo in COLUMNS:
            if colinfo.name in self.enabled_columns:
                attr = colinfo.name.lower().replace(' ', '_')
                cols.append((getattr(self, attr),
                             options(*colinfo.options)))


class StoryRow(urwid.Button, StoryListColumns):
    story_focus_map = {None: 'focused',
                       'active-story': 'focused-active-story',
                       'inactive-story': 'focused-inactive-story',
                       'starred-story': 'focused-starred-story',
                       'held-story': 'focused-held-story',
                       'marked-story': 'focused-marked-story',
    }

    def selectable(self):
        return True

    def __init__(self, app, story,
                 enabled_columns, callback=None):
        super(StoryRow, self).__init__('', on_press=callback, user_data=story.key)
        self.app = app
        self.story_key = story.key
        self.enabled_columns = enabled_columns
        self.title = mywid.SearchableText(u'', wrap='clip')
        self.id = mywid.SearchableText(u'')
        self.updated = mywid.SearchableText(u'')
        self.status = mywid.SearchableText(u'')
        self.creator = mywid.SearchableText(u'', wrap='clip')
        self.mark = False
        self.columns = urwid.Columns([], dividechars=1)
        self.row_style = urwid.AttrMap(self.columns, '')
        self._w = urwid.AttrMap(self.row_style, None, focus_map=self.story_focus_map)
        self.update(story)

    def search(self, search, attribute):
        if self.title.search(search, attribute):
            return True
        if self.id.search(search, attribute):
            return True
        if self.creator.search(search, attribute):
            return True
        if self.status.search(search, attribute):
            return True
        if self.updated.search(search, attribute):
            return True
        return False

    def update(self, story):
        if story.status != 'active' or story.hidden:
            style = 'inactive-story'
        else:
            style = 'active-story'
        title = story.title
        flag = ' '
        #if story.starred:
        #    flag = '*'
        #    style = 'starred-story'
        #if story.held:
        #    flag = '!'
        #    style = 'held-story'
        if self.mark:
            flag = '%'
            style = 'marked-story'
        title = flag + title
        self.row_style.set_attr_map({None: style})
        self.title.set_text(title)
        self.id.set_text(str(story.id))
        self.creator.set_text(story.creator_name)
        self.status.set_text(story.status)
        today = self.app.time(datetime.datetime.utcnow()).date()
        updated_time = self.app.time(story.updated)
        if updated_time:
            if today == updated_time.date():
                self.updated.set_text(updated_time.strftime("%I:%M %p").upper())
            else:
                self.updated.set_text(updated_time.strftime("%Y-%m-%d"))
        else:
            self.updated.set_text('Unknown')
        self.updateColumns()

class StoryListHeader(urwid.WidgetWrap, StoryListColumns):
    def __init__(self, enabled_columns):
        self.enabled_columns = enabled_columns
        self.title = urwid.Text(u'Title', wrap='clip')
        self.id = urwid.Text(u'ID')
        self.updated = urwid.Text(u'Updated')
        self.status = urwid.Text(u'Status')
        self.creator = urwid.Text(u'Creator', wrap='clip')
        self.columns = urwid.Columns([], dividechars=1)
        super(StoryListHeader, self).__init__(self.columns)

    def update(self):
        self.updateColumns()


@mouse_scroll_decorator.ScrollByWheel
class StoryListView(urwid.WidgetWrap, mywid.Searchable):
    required_columns = set(['ID', 'Title', 'Updated'])
    optional_columns = set([])

    def getCommands(self):
        if self.project_key:
            refresh_help = "Sync current project"
        else:
            refresh_help = "Sync subscribed projects"
        return [
            (keymap.TOGGLE_HELD,
             "Toggle the held flag for the currently selected story"),
            (keymap.TOGGLE_HIDDEN,
             "Toggle the hidden flag for the currently selected story"),
            (keymap.TOGGLE_LIST_ACTIVE,
             "Toggle whether only active or all changes are displayed"),
            (keymap.TOGGLE_STARRED,
             "Toggle the starred flag for the currently selected story"),
            (keymap.TOGGLE_MARK,
             "Toggle the process mark for the currently selected story"),
            (keymap.REFINE_STORY_SEARCH,
             "Refine the current search query"),
            (keymap.REFRESH,
             refresh_help),
            (keymap.SORT_BY_NUMBER,
             "Sort stories by number"),
            (keymap.SORT_BY_UPDATED,
             "Sort stories by how recently the story was updated"),
            (keymap.SORT_BY_REVERSE,
             "Reverse the sort"),
            (keymap.INTERACTIVE_SEARCH,
             "Interactive search"),
            ]

    def help(self):
        key = self.app.config.keymap.formatKeys
        commands = self.getCommands()
        return [(c[0], key(c[0]), c[1]) for c in commands]

    def __init__(self, app, query, query_desc=None, project_key=None,
                 active=False, sort_by=None, reverse=None):
        super(StoryListView, self).__init__(urwid.Pile([]))
        self.log = logging.getLogger('boartty.view.story_list')
        self.searchInit()
        self.app = app
        self.query = query
        self.query_desc = query_desc or query
        self.active = active
        self.story_rows = {}
        self.enabled_columns = set()
        for colinfo in COLUMNS:
            if (colinfo.name in self.required_columns or
                colinfo.name not in self.optional_columns):
                self.enabled_columns.add(colinfo.name)
        self.disabled_columns = set()
        self.listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.project_key = project_key
        if 'Project' not in self.required_columns and project_key is not None:
            self.enabled_columns.discard('Project')
            self.disabled_columns.add('Project')
        #storyboard: creator
        if 'Owner' not in self.required_columns and 'owner:' in query:
            # This could be or'd with something else, but probably
            # not.
            self.enabled_columns.discard('Owner')
            self.disabled_columns.add('Owner')
        self.sort_by = sort_by or app.config.story_list_options['sort-by']
        if reverse is not None:
            self.reverse = reverse
        else:
            self.reverse = app.config.story_list_options['reverse']
        self.header = StoryListHeader(self.enabled_columns)
        self.refresh()
        self._w.contents.append((app.header, ('pack', 1)))
        self._w.contents.append((urwid.Divider(), ('pack', 1)))
        self._w.contents.append((urwid.AttrWrap(self.header, 'table-header'), ('pack', 1)))
        self._w.contents.append((self.listbox, ('weight', 1)))
        self._w.set_focus(3)

    def interested(self, event):
        if not ((self.project_key is not None and
                 isinstance(event, sync.StoryAddedEvent) and
                 self.project_key in event.related_project_keys)
                or
                (self.project_key is None and
                 isinstance(event, sync.StoryAddedEvent))
                or
                (isinstance(event, sync.StoryUpdatedEvent) and
                 event.story_key in self.story_rows.keys())):
            self.log.debug("Ignoring refresh story list due to event %s" % (event,))
            return False
        self.log.debug("Refreshing story list due to event %s" % (event,))
        return True

    def refresh(self):
        unseen_keys = set(self.story_rows.keys())
        with self.app.db.getSession() as session:
            story_list = session.getStories(self.query, self.active,
                                            sort_by=self.sort_by)
            if self.active:
                self.title = (u'Active %d stories in %s' %
                    (len(story_list), self.query_desc))
            else:
                self.title = (u'All %d stories in %s' %
                    (len(story_list), self.query_desc))
            self.short_title = self.query_desc
            if '/' in self.short_title and ' ' not in self.short_title:
                i = self.short_title.rfind('/')
                self.short_title = self.short_title[i+1:]
            self.app.status.update(title=self.title)

            if 'Status' not in self.required_columns and self.active:
                self.enabled_columns.discard('Status')
                self.disabled_columns.add('Status')
            else:
                self.enabled_columns.add('Status')
                self.disabled_columns.discard('Status')
            self.chooseColumns()
            self.header.update()
            i = 0
            if self.reverse:
                story_list.reverse()
            new_rows = []
            if len(self.listbox.body):
                focus_pos = self.listbox.focus_position
                focus_row = self.listbox.body[focus_pos]
            else:
                focus_pos = 0
                focus_row = None
            for story in story_list:
                row = self.story_rows.get(story.key)
                if not row:
                    row = StoryRow(self.app, story,
                                    self.enabled_columns,
                                    callback=self.onSelect)
                    self.listbox.body.insert(i, row)
                    self.story_rows[story.key] = row
                else:
                    row.update(story)
                    unseen_keys.remove(story.key)
                new_rows.append(row)
                i += 1
            self.listbox.body[:] = new_rows
            if focus_row in self.listbox.body:
                pos = self.listbox.body.index(focus_row)
            else:
                pos = min(focus_pos, len(self.listbox.body)-1)
            self.listbox.body.set_focus(pos)
        for key in unseen_keys:
            row = self.story_rows[key]
            del self.story_rows[key]

    def chooseColumns(self):
        currently_enabled_columns = self.enabled_columns.copy()
        size = self.app.loop.screen.get_cols_rows()
        cols = size[0]
        for colinfo in COLUMNS:
            if (colinfo.name not in self.disabled_columns):
                cols -= colinfo.spacing

        for colinfo in COLUMNS:
            if colinfo.name in self.optional_columns:
                if cols >= colinfo.spacing:
                    self.enabled_columns.add(colinfo.name)
                    cols -= colinfo.spacing
                else:
                    self.enabled_columns.discard(colinfo.name)
        if currently_enabled_columns != self.enabled_columns:
            self.header.updateColumns()
            for key, value in six.iteritems(self.story_rows):
                value.updateColumns()

    def getQueryString(self):
        if self.project_key is not None:
            return "project:%s %s" % (self.query_desc, self.app.config.project_story_list_query)
            return self.app.config.project_story_list_query
        return self.query

    def clearStoryList(self):
        for key, value in six.iteritems(self.story_rows):
            self.listbox.body.remove(value)
        self.story_rows = {}

    def getNextStoryKey(self, story_key):
        row = self.story_rows.get(story_key)
        try:
            i = self.listbox.body.index(row)
        except ValueError:
            return None
        if i+1 >= len(self.listbox.body):
            return None
        row = self.listbox.body[i+1]
        return row.story_key

    def getPrevStoryKey(self, story_key):
        row = self.story_rows.get(story_key)
        try:
            i = self.listbox.body.index(row)
        except ValueError:
            return None
        if i <= 0:
            return None
        row = self.listbox.body[i-1]
        return row.story_key

    def toggleStarred(self, story_key):
        with self.app.db.getSession() as session:
            story = session.getStory(story_key)
            story.starred = not story.starred
            ret = story.starred
            story.pending_starred = True
        self.app.sync.submitTask(
            sync.StoryStarredTask(story_key, sync.HIGH_PRIORITY))
        return ret

    def toggleHeld(self, story_key):
        return self.app.toggleHeldStory(story_key)

    def toggleHidden(self, story_key):
        with self.app.db.getSession() as session:
            story = session.getStory(story_key)
            story.hidden = not story.hidden
            ret = story.hidden
            hidden_str = 'hidden' if story.hidden else 'visible'
            self.log.debug("Set story %s to %s", story_key, hidden_str)
        return ret

    def advance(self):
        pos = self.listbox.focus_position
        if pos < len(self.listbox.body)-1:
            pos += 1
            self.listbox.focus_position = pos

    def keypress(self, size, key):
        if self.searchKeypress(size, key):
            return None

        if not self.app.input_buffer:
            key = super(StoryListView, self).keypress(size, key)
        keys = self.app.input_buffer + [key]
        commands = self.app.config.keymap.getCommands(keys)
        ret = self.handleCommands(commands)
        if ret is True:
            if keymap.FURTHER_INPUT not in commands:
                self.app.clearInputBuffer()
            return None
        return key

    def onResize(self):
        self.chooseColumns()

    def handleCommands(self, commands):
        if keymap.TOGGLE_LIST_ACTIVE in commands:
            self.active = not self.active
            self.refresh()
            return True
        if keymap.TOGGLE_HIDDEN in commands:
            if not len(self.listbox.body):
                return True
            pos = self.listbox.focus_position
            story_key = self.listbox.body[pos].story_key
            hidden = self.toggleHidden(story_key)
            if hidden:
                # Here we can avoid a full refresh by just removing the particular
                # row from the story list
                row = self.story_rows[story_key]
                self.listbox.body.remove(row)
                del self.story_rows[story_key]
            else:
                # Just fall back on doing a full refresh if we're in a situation
                # where we're not just popping a row from the list of stories.
                self.refresh()
                self.advance()
            return True
        if keymap.TOGGLE_HELD in commands:
            if not len(self.listbox.body):
                return True
            pos = self.listbox.focus_position
            story_key = self.listbox.body[pos].story_key
            self.toggleHeld(story_key)
            row = self.story_rows[story_key]
            with self.app.db.getSession() as session:
                story = session.getStory(story_key)
                row.update(story)
            self.advance()
            return True
        if keymap.TOGGLE_STARRED in commands:
            if not len(self.listbox.body):
                return True
            pos = self.listbox.focus_position
            story_key = self.listbox.body[pos].story_key
            self.toggleStarred(story_key)
            row = self.story_rows[story_key]
            with self.app.db.getSession() as session:
                story = session.getStory(story_key)
                row.update(story)
            self.advance()
            return True
        if keymap.TOGGLE_MARK in commands:
            if not len(self.listbox.body):
                return True
            pos = self.listbox.focus_position
            story_key = self.listbox.body[pos].story_key
            row = self.story_rows[story_key]
            row.mark = not row.mark
            with self.app.db.getSession() as session:
                story = session.getStory(story_key)
                row.update(story)
            self.advance()
            return True
        if keymap.REFRESH in commands:
            if self.project_key:
                self.app.sync.submitTask(
                    sync.SyncProjectTask(self.project_key, sync.HIGH_PRIORITY))
            else:
                self.app.sync.submitTask(
                    sync.SyncSubscribedProjectsTask(sync.HIGH_PRIORITY))
            self.app.status.update()
            return True
        if keymap.SORT_BY_NUMBER in commands:
            if not len(self.listbox.body):
                return True
            self.sort_by = 'number'
            self.clearStoryList()
            self.refresh()
            return True
        if keymap.SORT_BY_UPDATED in commands:
            if not len(self.listbox.body):
                return True
            self.sort_by = 'updated'
            self.clearStoryList()
            self.refresh()
            return True
        if keymap.SORT_BY_REVERSE in commands:
            if not len(self.listbox.body):
                return True
            if self.reverse:
                self.reverse = False
            else:
                self.reverse = True
            self.clearStoryList()
            self.refresh()
            return True
        if keymap.REFINE_STORY_SEARCH in commands:
            default = self.getQueryString()
            self.app.searchDialog(default)
            return True
        if keymap.INTERACTIVE_SEARCH in commands:
            self.searchStart()
            return True
        return False

    def onSelect(self, button, story_key):
        self.app.openStory(story_key)
