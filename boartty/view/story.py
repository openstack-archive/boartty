# Copyright 2014 OpenStack Foundation
# Copyright 2014 Hewlett-Packard Development Company, L.P.
# Copyright 2016 Red Hat, Inc
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

import collections
import datetime
import logging
try:
    import ordereddict
except:
    pass
import textwrap

from six.moves.urllib import parse as urlparse
import urwid

from boartty import keymap
from boartty import mywid
from boartty import sync
from boartty.view import mouse_scroll_decorator
import boartty.view

try:
    OrderedDict = collections.OrderedDict
except AttributeError:
    OrderedDict = ordereddict.OrderedDict

class NewStoryDialog(urwid.WidgetWrap, mywid.LineBoxTitlePropertyMixin):
    signals = ['save', 'cancel']
    def __init__(self, app):
        self.app = app
        save_button = mywid.FixedButton(u'Save')
        cancel_button = mywid.FixedButton(u'Cancel')
        urwid.connect_signal(save_button, 'click',
            lambda button:self._emit('save'))
        urwid.connect_signal(cancel_button, 'click',
            lambda button:self._emit('cancel'))

        rows = []
        buttons = [('pack', save_button),
                   ('pack', cancel_button)]
        buttons = urwid.Columns(buttons, dividechars=2)

        self.project_button = ProjectButton(self.app)
        self.title_field = mywid.MyEdit(u'', edit_text=u'', ring=app.ring)
        self.description_field = mywid.MyEdit(u'', edit_text='',
                                              multiline=True, ring=app.ring)

        for (label, w) in [
                (u'Title:', self.title_field),
                (u'Description:', self.description_field),
                (u'Project:', ('pack', self.project_button)),
                ]:
            row = urwid.Columns([(12, urwid.Text(label)), w])
            rows.append(row)

        rows.append(urwid.Divider())
        rows.append(buttons)
        pile = urwid.Pile(rows)
        fill = urwid.Filler(pile, valign='top')
        super(NewStoryDialog, self).__init__(urwid.LineBox(fill, 'New Story'))

class ProjectButton(mywid.SearchSelectButton):
    def __init__(self, app, key=None, value=None):
        self.app = app
        super(ProjectButton, self).__init__(app, 'Select Project', key, value,
                                            self.getValues)

    def getValues(self):
        with self.app.db.getSession() as session:
            projects = session.getProjects()
        for project in projects:
            yield (project.key, project.name)

class StatusButton(mywid.SearchSelectButton):
    def __init__(self, app):
        self.app = app
        super(StatusButton, self).__init__(app, 'Select Status', 'todo', 'todo',
                                           self.getValues)

    def getValues(self):
        return [('todo', 'todo'),
                ('merged', 'merged'),
                ('invalid', 'invalid'),
                ('review', 'review'),
                ('inprogress', 'inprogress'),
        ]

class AssigneeButton(mywid.SearchSelectButton):
    def __init__(self, app):
        self.app = app
        super(AssigneeButton, self).__init__(app, 'Select Assignee', None, None,
                                             self.getValues)

    def getValues(self):
        with self.app.db.getSession() as session:
            users = session.getUsers()
        for user in users:
            yield (user.key, user.name)

class NewTaskDialog(urwid.WidgetWrap, mywid.LineBoxTitlePropertyMixin):
    signals = ['save', 'cancel']
    def __init__(self, app):
        self.app = app
        save_button = mywid.FixedButton(u'Save')
        cancel_button = mywid.FixedButton(u'Cancel')
        urwid.connect_signal(save_button, 'click',
            lambda button:self._emit('save'))
        urwid.connect_signal(cancel_button, 'click',
            lambda button:self._emit('cancel'))

        rows = []
        buttons = [('pack', save_button),
                   ('pack', cancel_button)]
        buttons = urwid.Columns(buttons, dividechars=2)

        self.project_button = ProjectButton(self.app)
        self.status_button = StatusButton(self.app)
        self.assignee_button = AssigneeButton(self.app)
        self.title_field = mywid.MyEdit(u'', edit_text=u'', ring=app.ring)

        for (label, w) in [
                (u'Project:', ('pack', self.project_button)),
                (u'Title:', self.title_field),
                (u'Status:', ('pack', self.status_button)),
                (u'Assignee:', ('pack', self.assignee_button)),
                ]:
            row = urwid.Columns([(12, urwid.Text(label)), w])
            rows.append(row)

        rows.append(urwid.Divider())
        rows.append(buttons)
        pile = urwid.Pile(rows)
        fill = urwid.Filler(pile, valign='top')
        super(NewTaskDialog, self).__init__(urwid.LineBox(fill, 'New Task'))

class TaskRow(urwid.WidgetWrap):
    task_focus_map = {
        'task-title': 'focused-task-title',
        'task-project': 'focused-task-project',
        'task-status': 'focused-task-status',
        'task-assignee': 'focused-task-assignee',
        'task-note': 'focused-task-note',
    }

    def keypress(self, size, key):
        if not self.app.input_buffer:
            key = super(TaskRow, self).keypress(size, key)
        keys = self.app.input_buffer + [key]
        commands = self.app.config.keymap.getCommands(keys)
        if keymap.DELETE_TASK in commands:
            self.delete()
            return None
        return key

    def __init__(self, app, story_view, task):
        super(TaskRow, self).__init__(urwid.Pile([]))
        self.app = app
        self.story_view = story_view
        self.task_key = task.key
        self._note = u''
        self.taskid = mywid.TextButton(self._note)
        urwid.connect_signal(self.taskid, 'click',
                             lambda b:self.editNote(b))
        self.project = ProjectButton(self.app)
        urwid.connect_signal(self.project, 'changed',
                             lambda b:self.updateProject(b))
        self.status = StatusButton(self.app)
        urwid.connect_signal(self.status, 'changed',
                             lambda b:self.updateStatus(b))
        self._title = u''
        self.title = mywid.TextButton(self._title)
        urwid.connect_signal(self.title, 'click',
                             lambda b:self.editTitle(b))
        self.assignee = AssigneeButton(self.app)
        urwid.connect_signal(self.assignee, 'changed',
                             lambda b:self.updateAssignee(b))
        self.description = urwid.Text(u'')
        self.columns = urwid.Columns([], dividechars=1)

        for (widget, attr, packing) in [
                (self.taskid, 'task-id', ('given', 4, False)),
                (self.project, 'task-project', ('weight', 1, False)),
                (self.title, 'task-title', ('weight', 2, False)),
                (self.status, 'task-status', ('weight', 1, False)),
                (self.assignee, 'task-assignee', ('weight', 1, False)),
        ]:
            w = urwid.AttrMap(urwid.Padding(widget, width='pack'), attr,
                              focus_map={'focused': 'focused-'+attr})
            self.columns.contents.append((w, packing))
        self.pile = urwid.Pile([self.columns])
        self.note = urwid.Text(u'')
        self.note_visible = False
        self.note_columns = urwid.Columns([], dividechars=1)
        self.note_columns.contents.append((urwid.Text(u''), ('given', 1, False)))
        self.note_columns.contents.append((self.note, ('weight', 1, False)))
        self._w = urwid.AttrMap(self.pile, None)#, focus_map=self.task_focus_map)
        self.refresh(task)

    def setNote(self, note):
        if note:
            self._note = note
            self.note.set_text(('task-note', self._note))
            if not self.note_visible:
                self.pile.contents.append((self.note_columns, ('weight', 1)))
                self.note_visible = True
        elif self.note_visible:
            for x in self.pile.contents[:]:
                if x[0] is self.note_columns:
                    self.pile.contents.remove(x)
                    self.note_visible = False

    def refresh(self, task):
        self.taskid.text.set_text(str(task.id))
        self.project.update(task.project.key, task.project.name)
        self.status.update(task.status, task.status)
        self._title = task.title
        self.title.text.set_text(self._title)
        self.setNote(task.link)
        if task.assignee:
            self.assignee.update(task.assignee.key, task.assignee.name)
        else:
            self.assignee.update(None, 'Unassigned')

    def updateProject(self, project_button):
        with self.app.db.getSession() as session:
            task = session.getTask(self.task_key)
            project = session.getProject(project_button.key)
            task.project = project
        self.app.sync.submitTask(
            sync.UpdateTaskTask(task.key, sync.HIGH_PRIORITY))

    def updateStatus(self, status_button):
        with self.app.db.getSession() as session:
            task = session.getTask(self.task_key)
            task.status = status_button.key
        self.app.sync.submitTask(
            sync.UpdateTaskTask(task.key, sync.HIGH_PRIORITY))

    def updateAssignee(self, assignee_button):
        with self.app.db.getSession() as session:
            task = session.getTask(self.task_key)
            user = session.getUser(assignee_button.key)
            task.assignee = user
        self.app.sync.submitTask(
            sync.UpdateTaskTask(task.key, sync.HIGH_PRIORITY))

    def editTitle(self, title_button):
        dialog = mywid.LineEditDialog(self.app, 'Edit Task Title', '',
                                      'Title: ', self._title,
                                      ring=self.app.ring)
        urwid.connect_signal(dialog, 'save',
            lambda button: self.updateTitle(dialog, True))
        urwid.connect_signal(dialog, 'cancel',
            lambda button: self.updateTitle(dialog, False))
        self.app.popup(dialog)

    def updateTitle(self, dialog, save):
        if save:
            with self.app.db.getSession() as session:
                task = session.getTask(self.task_key)
                task.title = dialog.entry.edit_text
            self._title = task.title
            self.title.text.set_text(self._title)
            self.app.sync.submitTask(
                sync.UpdateTaskTask(task.key, sync.HIGH_PRIORITY))
        self.app.backScreen()

    def editNote(self, note_button):
        dialog = mywid.LineEditDialog(self.app, 'Edit Task Note', '',
                                      'Note: ', self._note,
                                      ring=self.app.ring)
        urwid.connect_signal(dialog, 'save',
            lambda button: self.updateNote(dialog, True))
        urwid.connect_signal(dialog, 'cancel',
            lambda button: self.updateNote(dialog, False))
        self.app.popup(dialog)

    def updateNote(self, dialog, save):
        if save:
            with self.app.db.getSession() as session:
                task = session.getTask(self.task_key)
                task.link = dialog.entry.edit_text or None
            self.setNote(task.link)
            self.app.sync.submitTask(
                sync.UpdateTaskTask(task.key, sync.HIGH_PRIORITY))
        self.app.backScreen()

    def delete(self):
        dialog = mywid.YesNoDialog(u'Delete Task',
                                   u'Are you sure you want to delete this task?')
        urwid.connect_signal(dialog, 'no', lambda d: self.app.backScreen())
        urwid.connect_signal(dialog, 'yes', self.finishDelete)
        self.app.popup(dialog)

    def finishDelete(self, dialog):
        with self.app.db.getSession() as session:
            task = session.getTask(self.task_key)
            task.pending_delete = True
        self.app.sync.submitTask(
            sync.UpdateTaskTask(task.key, sync.HIGH_PRIORITY))
        self.app.backScreen()
        self.story_view.refresh()

class StoryButton(urwid.Button):
    button_left = urwid.Text(u' ')
    button_right = urwid.Text(u' ')

    def __init__(self, story_view, story_key, text):
        super(StoryButton, self).__init__('')
        self.set_label(text)
        self.story_view = story_view
        self.story_key = story_key
        urwid.connect_signal(self, 'click',
            lambda button: self.openStory())

    def set_label(self, text):
        super(StoryButton, self).set_label(text)

    def openStory(self):
        try:
            self.story_view.app.changeScreen(StoryView(self.story_view.app, self.story_key))
        except boartty.view.DisplayError as e:
            self.story_view.app.error(e.message)

class StoryEventBox(mywid.HyperText):
    def __init__(self, story_view, event):
        super(StoryEventBox, self).__init__(u'')
        self.story_view = story_view
        self.app = story_view.app
        self.refresh(event)

    def formatReply(self):
        text = self.comment_text
        pgraphs = []
        pgraph_accumulator = []
        wrap = True
        for line in text.split('\n'):
            if line.startswith('> '):
                wrap = False
                line = '> ' + line
            if not line:
                if pgraph_accumulator:
                    pgraphs.append((wrap, '\n'.join(pgraph_accumulator)))
                    pgraph_accumulator = []
                    wrap = True
                continue
            pgraph_accumulator.append(line)
        if pgraph_accumulator:
            pgraphs.append((wrap, '\n'.join(pgraph_accumulator)))
            pgraph_accumulator = []
            wrap = True
        wrapper = textwrap.TextWrapper(initial_indent='> ',
                                       subsequent_indent='> ')
        wrapped_pgraphs = []
        for wrap, pgraph in pgraphs:
            if wrap:
                wrapped_pgraphs.append('\n'.join(wrapper.wrap(pgraph)))
            else:
                wrapped_pgraphs.append(pgraph)
        return '\n>\n'.join(wrapped_pgraphs)

    def reply(self):
        reply_text = self.formatReply()
        if reply_text:
            reply_text = self.event_creator + ' wrote:\n\n' + reply_text + '\n'
        self.story_view.leaveComment(reply_text=reply_text)

    def refresh(self, event):
        self.event_id = event.id
        self.event_creator = event.creator_name
        description = event.description
        if event.comment:
            comment = event.comment.content
        else:
            comment = ''
        self.comment_text = comment
        created = self.app.time(event.created)
        lines = comment.split('\n')
        if event.creator.id == self.app.user_id:
            name_style = 'story-event-own-name'
            header_style = 'story-event-own-header'
            creator_string = event.creator.name
        else:
            name_style = 'story-event-name'
            header_style = 'story-event-header'
            if event.creator.email:
                creator_string = "%s <%s>" % (
                    event.creator.name,
                    event.creator.email)
            else:
                creator_string = event.creator.name

        text = [(name_style, creator_string),
                (header_style, ': '+description),
                (header_style,
                 created.strftime(' (%Y-%m-%d %H:%M:%S%z)'))]
        if event.comment and event.comment.draft and not event.comment.pending:
            text.append(('story-event-draft', ' (draft)'))
        elif event.comment:
            link = mywid.Link('< Reply >',
                              'story-event-button',
                              'focused-story-event-button')
            urwid.connect_signal(link, 'selected',
                                 lambda link:self.reply())
            text.append(' ')
            text.append(link)
        text.append('\n')
        if lines and lines[-1]:
            lines.append('')
        comment_text = ['\n'.join(lines)]
        for commentlink in self.app.config.commentlinks:
            comment_text = commentlink.run(self.app, comment_text)
        info = event.info or ''
        if info:
            info = [info + '\n']
        else:
            info = []
        self.set_text(text+comment_text+info)

class DescriptionBox(mywid.HyperText):
    def __init__(self, app, description):
        self.app = app
        super(DescriptionBox, self).__init__(description)

    def set_text(self, text):
        text = [text]
        for commentlink in self.app.config.commentlinks:
            text = commentlink.run(self.app, text)
        super(DescriptionBox, self).set_text(text)

@mouse_scroll_decorator.ScrollByWheel
class StoryView(urwid.WidgetWrap):
    def getCommands(self):
        return [
            (keymap.TOGGLE_HIDDEN,
             "Toggle the hidden flag for the current story"),
            (keymap.NEXT_STORY,
             "Go to the next story in the list"),
            (keymap.PREV_STORY,
             "Go to the previous story in the list"),
            (keymap.LEAVE_COMMENT,
             "Leave a comment on the story"),
            (keymap.NEW_TASK,
             "Add a new task to the current story"),
            (keymap.TOGGLE_HELD,
             "Toggle the held flag for the current story"),
            (keymap.TOGGLE_HIDDEN_COMMENTS,
             "Toggle display of hidden comments"),
            (keymap.SEARCH_RESULTS,
             "Back to the list of stories"),
            (keymap.TOGGLE_STARRED,
             "Toggle the starred flag for the current story"),
            (keymap.EDIT_DESCRIPTION,
             "Edit the commit message of this story"),
            (keymap.REFRESH,
             "Refresh this story"),
            (keymap.EDIT_TITLE,
             "Edit the title of this story"),
            ]

    def help(self):
        key = self.app.config.keymap.formatKeys
        commands = self.getCommands()
        ret = [(c[0], key(c[0]), c[1]) for c in commands]
        for k in self.app.config.reviewkeys.values():
            action = ', '.join(['{category}:{value}'.format(**a) for a in k['approvals']])
            ret.append(('', keymap.formatKey(k['key']), action))
        return ret

    def __init__(self, app, story_key):
        super(StoryView, self).__init__(urwid.Pile([]))
        self.log = logging.getLogger('boartty.view.story')
        self.app = app
        self.story_key = story_key
        self.task_rows = {}
        self.event_rows = {}
        self.hide_events = True
        self.marked_seen = False
        self.title_label = urwid.Text(u'', wrap='clip')
        self.creator_label = mywid.TextButton(u'', on_press=self.searchCreator)
        self.tags_label = urwid.Text(u'', wrap='clip')
        self.created_label = urwid.Text(u'', wrap='clip')
        self.updated_label = urwid.Text(u'', wrap='clip')
        self.status_label = urwid.Text(u'', wrap='clip')
        self.permalink_label = mywid.TextButton(u'', on_press=self.openPermalink)
        story_info = []
        story_info_map={'story-data': 'focused-story-data'}
        for l, v in [("Title", self.title_label),
                     ("Creator", urwid.Padding(urwid.AttrMap(self.creator_label, None,
                                                           focus_map=story_info_map),
                                             width='pack')),
                     ("Tags", urwid.Padding(urwid.AttrMap(self.tags_label, None,
                                                           focus_map=story_info_map),
                                             width='pack')),
                     ("Created", self.created_label),
                     ("Updated", self.updated_label),
                     ("Status", self.status_label),
                     ("Permalink", urwid.Padding(urwid.AttrMap(self.permalink_label, None,
                                                               focus_map=story_info_map),
                                                 width='pack')),
                     ]:
            row = urwid.Columns([(12, urwid.Text(('story-header', l), wrap='clip')), v])
            story_info.append(row)
        story_info = urwid.Pile(story_info)
        self.description = DescriptionBox(app, u'')
        self.listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self._w.contents.append((self.app.header, ('pack', 1)))
        self._w.contents.append((urwid.Divider(), ('pack', 1)))
        self._w.contents.append((self.listbox, ('weight', 1)))
        self._w.set_focus(2)

        self.listbox.body.append(story_info)
        self.listbox.body.append(urwid.Divider())
        self.listbox_tasks_start = len(self.listbox.body)
        self.listbox.body.append(urwid.Divider())
        self.listbox.body.append(self.description)
        self.listbox.body.append(urwid.Divider())

        self.refresh()
        self.listbox.set_focus(3)

    def interested(self, event):
        if not ((isinstance(event, sync.StoryAddedEvent) and
                 self.story_key == event.story_key)
                or
                (isinstance(event, sync.StoryUpdatedEvent) and
                 self.story_key == event.story_key)):
            self.log.debug("Ignoring refresh story due to event %s" % (event,))
            return False
        self.log.debug("Refreshing story due to event %s" % (event,))
        return True

    def refresh(self):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            # When we first open the story, update its last_seen
            # time.
            if not self.marked_seen:
                story.last_seen = datetime.datetime.utcnow()
                self.marked_seen = True
            hidden = starred = held = ''
            # storyboard
            #if story.hidden:
            #    hidden = ' (hidden)'
            #if story.starred:
            #    starred = '* '
            #if story.held:
            #    held = ' (held)'
            self.title = '%sStory %s%s%s' % (starred, story.id,
                                                hidden, held)
            self.app.status.update(title=self.title)
            self.story_rest_id = story.id
            self.story_title = story.title
            if story.creator:
                self.creator_email = story.creator.email
            else:
                self.creator_email = None

            if self.creator_email:
                creator_string = '%s <%s>' % (story.creator_name,
                                              story.creator.email)
            else:
                creator_string = story.creator_name
            self.creator_label.text.set_text(('story-data', creator_string))
            tags_string = ' '.join([t.name for t in story.tags])
            self.tags_label.set_text(('story-data', tags_string))
            self.title_label.set_text(('story-data', story.title))
            self.created_label.set_text(('story-data', str(self.app.time(story.created))))
            self.updated_label.set_text(('story-data', str(self.app.time(story.updated))))
            self.status_label.set_text(('story-data', story.status))
            self.permalink_url = '' # storyboard urlparse.urljoin(self.app.config.url, str(story.number))
            self.permalink_label.text.set_text(('story-data', self.permalink_url))
            self.description.set_text(story.description)

            # The listbox has both tasks and events in it, so
            # keep track of the index separate from the loop.
            listbox_index = self.listbox_tasks_start
            # The set of task keys currently displayed
            unseen_keys = set(self.task_rows.keys())
            for task in story.tasks:
                self.log.debug(task)
                if task.pending_delete:
                    continue
                row = self.task_rows.get(task.key)
                if not row:
                    row = TaskRow(self.app, self, task)
                    self.listbox.body.insert(listbox_index, row)
                    self.task_rows[task.key] = row
                else:
                    unseen_keys.remove(task.key)
                row.refresh(task)
                listbox_index += 1
            # Remove any events that should not be displayed
            for key in unseen_keys:
                row = self.task_rows.get(key)
                self.listbox.body.remove(row)
                del self.task_rows[key]
                listbox_index -= 1

            listbox_index = len(self.listbox.body)
            # Get the set of events that should be displayed
            display_events = []
            for event in story.events:
                if event.comment or (not self.hide_events):
                    display_events.append(event)
            # The set of event keys currently displayed
            unseen_keys = set(self.event_rows.keys())
            # Make sure all of the events that should be displayed are
            for event in display_events:
                row = self.event_rows.get(event.key)
                if not row:
                    box = StoryEventBox(self, event)
                    row = urwid.Padding(box, width=80)
                    self.listbox.body.insert(listbox_index, row)
                    self.event_rows[event.key] = row
                else:
                    unseen_keys.remove(event.key)
                    row.original_widget.refresh(event)
                listbox_index += 1
            # Remove any events that should not be displayed
            for key in unseen_keys:
                row = self.event_rows.get(key)
                self.listbox.body.remove(row)
                del self.event_rows[key]
                listbox_index -= 1

    def toggleHidden(self):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            story.hidden = not story.hidden
            self.app.project_cache.clear(story.project)

    def toggleStarred(self):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            story.starred = not story.starred
            story.pending_starred = True
        self.app.sync.submitTask(
            sync.StoryStarredTask(self.story_key, sync.HIGH_PRIORITY))

    def toggleHeld(self):
        return self.app.toggleHeldStory(self.story_key)

    def keypress(self, size, key):
        if not self.app.input_buffer:
            key = super(StoryView, self).keypress(size, key)
        keys = self.app.input_buffer + [key]
        commands = self.app.config.keymap.getCommands(keys)
        if keymap.TOGGLE_HIDDEN in commands:
            self.toggleHidden()
            self.refresh()
            return None
        if keymap.TOGGLE_STARRED in commands:
            self.toggleStarred()
            self.refresh()
            return None
        if keymap.TOGGLE_HELD in commands:
            self.toggleHeld()
            self.refresh()
            return None
        if keymap.LEAVE_COMMENT in commands:
            self.leaveComment()
            return None
        if keymap.NEW_TASK in commands:
            self.newTask()
            return None
        if keymap.SEARCH_RESULTS in commands:
            widget = self.app.findStoryList()
            if widget:
                self.app.backScreen(widget)
            return None
        if ((keymap.NEXT_STORY in commands) or
            (keymap.PREV_STORY in commands)):
            widget = self.app.findStoryList()
            if widget:
                if keymap.NEXT_STORY in commands:
                    new_story_key = widget.getNextStoryKey(self.story_key)
                else:
                    new_story_key = widget.getPrevStoryKey(self.story_key)
                if new_story_key:
                    try:
                        view = StoryView(self.app, new_story_key)
                        self.app.changeScreen(view, push=False)
                    except boartty.view.DisplayError as e:
                        self.app.error(e.message)
            return None
        if keymap.TOGGLE_HIDDEN_COMMENTS in commands:
            self.hide_events = not self.hide_events
            self.refresh()
            return None
        if keymap.EDIT_DESCRIPTION in commands:
            self.editDescription()
            return None
        if keymap.REFRESH in commands:
            self.app.sync.submitTask(
                sync.SyncStoryTask(self.story_rest_id, priority=sync.HIGH_PRIORITY))
            self.app.status.update()
            return None
        if keymap.EDIT_TITLE in commands:
            self.editTitle()
            return None
        return key

    def editDescription(self):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            dialog = mywid.TextEditDialog(self.app, u'Edit Description',
                                          u'Description:',
                                          u'Save', story.description)
        urwid.connect_signal(dialog, 'cancel', self.app.backScreen)
        urwid.connect_signal(dialog, 'save', lambda button:
                                 self.doEditDescription(dialog))
        self.app.popup(dialog,
                       relative_width=50, relative_height=75,
                       min_width=60, min_height=20)

    def doEditDescription(self, dialog):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            story.description = dialog.entry.edit_text
            story.pending = True
        self.app.sync.submitTask(
            sync.UpdateStoryTask(self.story_key, sync.HIGH_PRIORITY))
        self.app.backScreen()
        self.refresh()

    def leaveComment(self, parent=None, reply_text=None):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            event = story.getDraftCommentEvent(parent)
            if event:
                text = event.comment.content
            else:
                text = u''
            if reply_text:
                text += reply_text
            dialog = mywid.TextEditDialog(self.app, u'Leave Comment', u'Comment:',
                                          u'Save', text)
        urwid.connect_signal(dialog, 'cancel', lambda button:
                             self.cancelLeaveComment(dialog, parent))
        urwid.connect_signal(dialog, 'save', lambda button:
                             self.saveLeaveComment(dialog, parent))
        self.app.popup(dialog,
                       relative_width=50, relative_height=75,
                       min_width=60, min_height=20)

    def cancelLeaveComment(self, dialog, parent):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            user = session.getUser(self.app.user_id)
            story.setDraftComment(user, parent, dialog.entry.edit_text)
        self.app.backScreen()
        self.refresh()

    def saveLeaveComment(self, dialog, parent):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            user = session.getUser(self.app.user_id)
            event = story.setDraftComment(user, parent, dialog.entry.edit_text)
            event.comment.pending = True
        self.app.sync.submitTask(
            sync.AddCommentTask(event.key, sync.HIGH_PRIORITY))
        self.app.backScreen()
        self.refresh()

    def newTask(self):
        dialog = NewTaskDialog(self.app)
        urwid.connect_signal(dialog, 'save',
                             lambda button: self.saveNewTask(dialog))
        urwid.connect_signal(dialog, 'cancel',
                             lambda button: self.cancelNewTask(dialog))
        self.app.popup(dialog,
                       relative_width=50, relative_height=25,
                       min_width=60, min_height=8)

    def cancelNewTask(self, dialog):
        self.app.backScreen()

    def saveNewTask(self, dialog):
        with self.app.db.getSession() as session:
            story = session.getStory(self.story_key)
            task = story.addTask()
            task.project = session.getProjectByID(dialog.project_button.key)
            task.title = dialog.title_field.edit_text
            task.status = dialog.status_button.key
            if dialog.assignee_button.key:
                task.assignee = session.getUserByID(dialog.assignee_button.key)
            task.pending = True

        self.app.sync.submitTask(
            sync.UpdateTaskTask(task.key, sync.HIGH_PRIORITY))
        self.app.backScreen()
        self.refresh()

    def editTitle(self):
        dialog = mywid.LineEditDialog(self.app, 'Edit Story Title', '',
                                      'Title: ', self.story_title,
                                      ring=self.app.ring)
        urwid.connect_signal(dialog, 'save',
            lambda button: self.updateTitle(dialog, True))
        urwid.connect_signal(dialog, 'cancel',
            lambda button: self.updateTitle(dialog, False))
        self.app.popup(dialog)

    def updateTitle(self, dialog, save):
        if save:
            with self.app.db.getSession() as session:
                story = session.getStory(self.story_key)
                story.title = dialog.entry.edit_text
            self.app.sync.submitTask(
                sync.UpdateStoryTask(story.key, sync.HIGH_PRIORITY))
        self.app.backScreen()
        self.refresh()

    def openPermalink(self, widget):
        self.app.openURL(self.permalink_url)

    def searchCreator(self, widget):
        if self.creator_email:
            self.app.doSearch("status:open creator:%s" % (self.creator_email,))

    def searchTags(self, widget):
        #storyboard
        if self.topic:
            self.app.doSearch("status:open topic:%s" % (self.topic,))
