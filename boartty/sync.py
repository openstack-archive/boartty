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

import collections
import errno
import logging
import math
import os
import re
import threading
import json
import time
import datetime

import dateutil.parser
import dateutil.tz
try:
    import ordereddict
except:
    pass
import requests
import requests.utils
import six
from six.moves import queue
from six.moves.urllib import parse as urlparse

import boartty.version

HIGH_PRIORITY=0
NORMAL_PRIORITY=1
LOW_PRIORITY=2

TIMEOUT=30


class OfflineError(Exception):
    pass

class MultiQueue(object):
    def __init__(self, priorities):
        try:
            self.queues = collections.OrderedDict()
        except AttributeError:
            self.queues = ordereddict.OrderedDict()
        for key in priorities:
            self.queues[key] = collections.deque()
        self.condition = threading.Condition()
        self.incomplete = []

    def qsize(self):
        count = 0
        self.condition.acquire()
        try:
            for queue in self.queues.values():
                count += len(queue)
            return count + len(self.incomplete)
        finally:
            self.condition.release()

    def put(self, item, priority):
        added = False
        self.condition.acquire()
        try:
            if item not in self.queues[priority]:
                self.queues[priority].append(item)
                added = True
            self.condition.notify()
        finally:
            self.condition.release()
        return added

    def get(self):
        self.condition.acquire()
        try:
            while True:
                for queue in self.queues.values():
                    try:
                        ret = queue.popleft()
                        self.incomplete.append(ret)
                        return ret
                    except IndexError:
                        pass
                self.condition.wait()
        finally:
            self.condition.release()

    def find(self, klass, priority):
        results = []
        self.condition.acquire()
        try:
            for item in self.queues[priority]:
                if isinstance(item, klass):
                    results.append(item)
        finally:
            self.condition.release()
        return results

    def complete(self, item):
        self.condition.acquire()
        try:
            if item in self.incomplete:
                self.incomplete.remove(item)
        finally:
            self.condition.release()


class UpdateEvent(object):
    def updateRelatedProjects(self, story):
        self.related_project_keys = set([task.project.key for task in story.tasks])

class ProjectAddedEvent(UpdateEvent):
    def __repr__(self):
        return '<ProjectAddedEvent project_key:%s>' % (
            self.project_key,)

    def __init__(self, project):
        self.project_key = project.key

class StoryAddedEvent(UpdateEvent):
    def __repr__(self):
        return '<StoryAddedEvent story_key:%s>' % (
            self.story_key)

    def __init__(self, story):
        self.story_key = story.key
        self.updateRelatedProjects(story)

class StoryUpdatedEvent(UpdateEvent):
    def __repr__(self):
        return '<StoryUpdatedEvent story_key:%s>' % (
            self.story_key)

    def __init__(self, story, status_changed=False):
        self.story_key = story.key
        self.status_changed = status_changed
        self.updateRelatedProjects(story)

class BoardAddedEvent(UpdateEvent):
    def __repr__(self):
        return '<BoardAddedEvent board_key:%s>' % (
            self.board_key)

    def __init__(self, board):
        self.board_key = board.key

class BoardUpdatedEvent(UpdateEvent):
    def __repr__(self):
        return '<BoardUpdatedEvent board_key:%s>' % (
            self.board_key)

    def __init__(self, board):
        self.board_key = board.key

class WorklistAddedEvent(UpdateEvent):
    def __repr__(self):
        return '<WorklistAddedEvent worklist_key:%s>' % (
            self.worklist_key)

    def __init__(self, worklist):
        self.worklist_key = worklist.key

class WorklistUpdatedEvent(UpdateEvent):
    def __repr__(self):
        return '<WorklistUpdatedEvent worklist_key:%s>' % (
            self.worklist_key)

    def __init__(self, worklist):
        self.worklist_key = worklist.key

def parseDateTime(dt):
    if dt is None:
        return None
    return dateutil.parser.parse(dt).astimezone(dateutil.tz.tzutc()).replace(
        tzinfo=None)

def formatDateTime(dt):
    if dt is None:
        return None
    return str(dt) + '+00:00'

def reference(obj):
    if obj is None:
        return None
    return obj.id

def getUser(sync, session, user_id):
    if user_id is None:
        return None
    user = session.getUserByID(user_id)
    if user:
        return user
    remote = sync.get('v1/users/%s' % user_id)
    user = session.createUser(remote['id'],
                                    remote.get('full_name'),
                                    remote.get('email'))
    return user

def syncStories(sync, priority, **kw):
    app = sync.app
    params = {}
    for k,v in kw.items():
        if v is not None:
            params[k] = v
    params = urlparse.urlencode(params)
    remote = sync.get('v1/stories?%s' % (params,))

    tasks = []
    for remote_story in remote:
        t = SyncStoryTask(remote_story['id'], remote_story,
                          priority=priority)
        sync.submitTask(t)
        tasks.append(t)
    return tasks

class Task(object):
    def __init__(self, priority=NORMAL_PRIORITY):
        self.log = logging.getLogger('boartty.sync')
        self.priority = priority
        self.succeeded = None
        self.event = threading.Event()
        self.tasks = []
        self.results = []

    def complete(self, success):
        self.succeeded = success
        self.event.set()

    def wait(self, timeout=None):
        self.event.wait(timeout)
        return self.succeeded

    def __eq__(self, other):
        raise NotImplementedError()

class SyncOwnUserTask(Task):
    def __repr__(self):
        return '<SyncOwnUserTask>'

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def run(self, sync):
        app = sync.app

        user = sync.get('v1/users/self')
        app.setUserID(user['id'])


class GetVersionTask(Task):
    def __repr__(self):
        return '<GetVersionTask>'

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def run(self, sync):
        systeminfo = sync.get('v1/systeminfo')
        sync.setRemoteVersion(systeminfo['version'])

class SyncProjectListTask(Task):
    def __repr__(self):
        return '<SyncProjectListTask>'

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def run(self, sync):
        app = sync.app
        remote = sync.get('v1/projects')
        remote_projects = {}
        for p in remote:
            remote_projects[p['id']] = p
        remote_ids = set(remote_projects.keys())
        with app.db.getSession() as session:
            local_projects = {}
            for p in session.getProjects():
                local_projects[p.id] = p
            local_ids = set(local_projects.keys())

            for pid in local_ids-remote_ids:
                session.delete(local_projects[pid])

            for pid in remote_ids-local_ids:
                p = remote_projects[pid]
                project = session.createProject(pid, p['name'],
                                                description=p.get('description', ''))
                self.log.info("Created project %s", project.name)
                self.results.append(ProjectAddedEvent(project))

class SyncUserListTask(Task):
    def __repr__(self):
        return '<SyncUserListTask>'

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def run(self, sync):
        app = sync.app
        remote = sync.get('v1/users')
        remote_users = {}
        for u in remote:
            remote_users[u['id']] = u
        remote_ids = set(remote_users.keys())
        with app.db.getSession() as session:
            local_users = {}
            for u in session.getUsers():
                local_users[u.id] = u
            local_ids = set(local_users.keys())

            for uid in local_ids-remote_ids:
                session.delete(local_users[uid])

            for uid in remote_ids-local_ids:
                u = remote_users[uid]
                user = session.createUser(uid, u['full_name'],
                                             email=u.get('email', ''))
                self.log.info("Created user %s", user.name)

class SyncProjectSubscriptionsTask(Task):
    def __repr__(self):
        return '<SyncProjectSubscriptionsTask>'

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def run(self, sync):
        app = sync.app
        remote = sync.get('v1/subscriptions?user_id=%s&target_type=project' % app.user_id)
        remote_ids = set()
        for s in remote:
            remote_ids.add(s['target_id'])

        with app.db.getSession() as session:
            for p in session.getProjects():
                p.subscribed = p.id in remote_ids

class SyncSubscribedProjectBranchesTask(Task):
    def __repr__(self):
        return '<SyncSubscribedProjectBranchesTask>'

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            projects = session.getProjects(subscribed=True)
        for p in projects:
            sync.submitTask(SyncProjectBranchesTask(p.name, self.priority))

class SyncProjectBranchesTask(Task):
    branch_re = re.compile(r'refs/heads/(.*)')

    def __init__(self, project_name, priority=NORMAL_PRIORITY):
        super(SyncProjectBranchesTask, self).__init__(priority)
        self.project_name = project_name

    def __repr__(self):
        return '<SyncProjectBranchesTask %s>' % (self.project_name,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.project_name == self.project_name):
            return True
        return False

    def run(self, sync):
        app = sync.app
        remote = sync.get('projects/%s/branches/' % urlparse.quote_plus(self.project_name))
        remote_branches = set()
        for x in remote:
            m = self.branch_re.match(x['ref'])
            if m:
                remote_branches.add(m.group(1))
        with app.db.getSession() as session:
            local = {}
            project = session.getProjectByName(self.project_name)
            for branch in project.branches:
                local[branch.name] = branch
            local_branches = set(local.keys())

            for name in local_branches-remote_branches:
                session.delete(local[name])
                self.log.info("Deleted branch %s from project %s in local DB.", name, project.name)

            for name in remote_branches-local_branches:
                project.createBranch(name)
                self.log.info("Added branch %s to project %s in local DB.", name, project.name)

class SyncSubscribedProjectsTask(Task):
    def __repr__(self):
        return '<SyncSubscribedProjectsTask>'

    def __eq__(self, other):
        if (other.__class__ == self.__class__):
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            keys = [p.key for p in session.getProjects(subscribed=True)]
        for key in keys:
            t = SyncProjectTask(key, self.priority)
            self.tasks.append(t)
            sync.submitTask(t)
        #t = SyncQueriedChangesTask('owner', 'is:owner', self.priority)
        #self.tasks.append(t)
        #sync.submitTask(t)
        #t = SyncQueriedChangesTask('starred', 'is:starred', self.priority)
        #self.tasks.append(t)
        #sync.submitTask(t)

class SyncProjectTask(Task):
    def __init__(self, project_key, priority=NORMAL_PRIORITY):
        super(SyncProjectTask, self).__init__(priority)
        self.project_key = project_key

    def __repr__(self):
        return '<SyncProjectTask %s>' % (self.project_key,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.project_key == self.project_key):
            return True
        return False

    def run(self, sync):
        app = sync.app
        now = datetime.datetime.utcnow()
        with app.db.getSession() as session:
            project = session.getProject(self.project_key)
        tasks = syncStories(sync, self.priority,
                            project_id=project.id,
                            updated_since=formatDateTime(project.updated))
        self.tasks.extend(tasks)
        t = SetProjectUpdatedTask(self.project_key, now,
                                  priority=self.priority)
        sync.submitTask(t)
        self.tasks.append(t)

class SyncStoryTask(Task):
    def __init__(self, story_id, data=None, priority=NORMAL_PRIORITY):
        super(SyncStoryTask, self).__init__(priority)
        self.story_id = story_id
        self.data = data

    def __repr__(self):
        return '<SyncStoryTask %s>' % (self.story_id,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.story_id == self.story_id and
            other.data == self.data):
            return True
        return False

    def updateTags(self, session, story, remote_tags):
        current_tags = set([t.id for t in story.tags])
        new_tags = set([t['id'] for t in remote_tags])
        to_add = new_tags - current_tags
        to_remove = current_tags - new_tags
        for remote_tag in remote_tags:
            tag_id = remote_tag['id']
            if tag_id in to_add:
                tag = session.getTagByID(tag_id)
                if tag is None:
                    tag = session.createTag(tag_id, remote_tag['name'])
                story.tags.append(tag)
        for local_tag in story.tags[:]:
            if local_tag.id in to_remove:
                story.tags.remove(local_tag)

    def updateTasks(self, sync, session, story, remote_tasks):
        local_tasks = dict([(t.id, t) for t in story.tasks])
        local_task_ids = set(local_tasks.keys())
        remote_task_ids = set([t['id'] for t in remote_tasks])
        to_add = remote_task_ids - local_task_ids
        to_remove = local_task_ids - remote_task_ids
        for remote_task in remote_tasks:
            task = session.getTaskByID(remote_task['id'])
            if task is None:
                self.log.debug("Adding to story id %s task %s" %
                               (story.id, remote_task,))
                task = story.addTask(remote_task['id'])
            task.title = remote_task['title']
            task.status = remote_task['status']
            task.created = parseDateTime(remote_task['created_at'])
            task.creator = getUser(sync, session, remote_task['creator_id'])
            task.assignee = getUser(sync, session, remote_task['assignee_id'])
            task.project = session.getProjectByID(remote_task['project_id'])
            task.link = remote_task['link']
            sync.app.project_cache.clear(task.project)

        for task_id in to_remove:
            self.log.debug("Removing from story id %s task %s" %
                           (story.id, task_id,))
            task = session.getTaskByID(task_id)
            sync.app.project_cache.clear(task.project)
            session.delete(task)

    def updateEvents(self, sync, session, story, remote_events):
        local_events = set([e.id for e in story.events])
        for remote_event in remote_events:
            if remote_event['id'] in local_events:
                continue
            self.log.debug("Adding to story id %s event %s" %
                           (story.id, remote_event,))
            remote_created = parseDateTime(remote_event['created_at'])
            user = getUser(sync, session, remote_event['author_id'])
            event = story.addEvent(remote_event['id'],
                                   remote_event['event_type'],
                                   user,
                                   remote_created,
                                   remote_event['event_info'])
            if 'comment' in remote_event:
                remote_comment = remote_event['comment']
                event.addComment(remote_comment['id'],
                                 remote_comment['content'],
                                 remote_comment['in_reply_to'])

    def run(self, sync):
        app = sync.app
        if self.data is None:
            remote_story = sync.get('v1/stories/%s' % (self.story_id,))
        else:
            remote_story = self.data

        remote_tags = sync.get('v1/stories/%s/tags' % (self.story_id,))
        remote_tasks = sync.get('v1/stories/%s/tasks' % (self.story_id,))
        remote_events = sync.get('v1/stories/%s/events' % (self.story_id,))
        with app.db.getSession() as session:
            story = session.getStoryByID(remote_story['id'])
            added = False
            if not story:
                story = session.createStory(remote_story['id'])
                sync.log.info("Created new story %s in local DB.", story.id)
                added = True
            story.title = remote_story['title']
            story.description = remote_story['description']
            story.updated = parseDateTime(remote_story['updated_at'])
            story.creator = getUser(sync, session,
                                    remote_story['creator_id'])
            story.created = parseDateTime(remote_story['created_at'])

            if story.status != remote_story.get('status'):
                status_changed = True
                story.status = remote_story.get('status')
            else:
                status_changed = False

            self.updateTags(session, story, remote_tags)
            self.updateTasks(sync, session, story, remote_tasks)
            self.updateEvents(sync, session, story, remote_events)

            if added:
                self.results.append(StoryAddedEvent(story))
            else:
                self.results.append(StoryUpdatedEvent(story,
                                                      status_changed=status_changed))

class SyncStoryByTaskTask(Task):
    def __init__(self, task_id, priority=NORMAL_PRIORITY):
        super(SyncStoryByTaskTask, self).__init__(priority)
        self.task_id = task_id

    def __repr__(self):
        return '<SyncStoryByTaskTask %s>' % (self.task_id,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.task_id == self.task_id):
            return True
        return False

    def run(self, sync):
        app = sync.app
        remote = sync.get('v1/tasks/%s' % (self.task_id,))

        self.tasks.append(sync.submitTask(SyncStoryTask(
            remote['story_id'], priority=self.priority)))

class SetProjectUpdatedTask(Task):
    def __init__(self, project_key, updated, priority=NORMAL_PRIORITY):
        super(SetProjectUpdatedTask, self).__init__(priority)
        self.project_key = project_key
        self.updated = updated

    def __repr__(self):
        return '<SetProjectUpdatedTask %s %s>' % (self.project_key, self.updated)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.project_key == self.project_key and
            other.updated == self.updated):
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            project = session.getProject(self.project_key)
            project.updated = self.updated

class SyncBoardsTask(Task):
    def __init__(self, priority=NORMAL_PRIORITY):
        super(SyncBoardsTask, self).__init__(priority)

    def __repr__(self):
        return '<SyncBoardsTask>'

    def __eq__(self, other):
        if (other.__class__ == self.__class__):
            return True
        return False

    #TODO: updated since, deleted
    def run(self, sync):
        app = sync.app
        remote = sync.get('v1/boards')

        for remote_board in remote:
            t = SyncBoardTask(remote_board['id'], remote_board,
                              priority=self.priority)
            sync.submitTask(t)
            self.tasks.append(t)

class SyncWorklistsTask(Task):
    def __init__(self, priority=NORMAL_PRIORITY):
        super(SyncWorklistsTask, self).__init__(priority)

    def __repr__(self):
        return '<SyncWorklistsTask>'

    def __eq__(self, other):
        if (other.__class__ == self.__class__):
            return True
        return False

    #TODO: updated since, deleted
    def run(self, sync):
        app = sync.app
        remote = sync.get('v1/worklists')

        for remote_worklist in remote:
            t = SyncWorklistTask(remote_worklist['id'], remote_worklist,
                                 priority=self.priority)
            sync.submitTask(t)
            self.tasks.append(t)

class SyncBoardTask(Task):
    def __init__(self, board_id, data=None, priority=NORMAL_PRIORITY):
        super(SyncBoardTask, self).__init__(priority)
        self.board_id = board_id
        self.data = data

    def __repr__(self):
        return '<SyncBoardTask %s>' % (self.board_id,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.board_id == self.board_id and
            other.data == self.data):
            return True
        return False

    def updateLanes(self, sync, session, board, remote_lanes):
        local_lane_ids = set([l.id for l in board.lanes])
        remote_lane_ids = set()
        for remote_lane in remote_lanes:
            remote_lane_ids.add(remote_lane['id'])
            if remote_lane['id'] not in local_lane_ids:
                self.log.debug("Adding to board id %s lane %s" %
                               (board.id, remote_lane,))
                remote_created = parseDateTime(remote_lane['created_at'])
                lane = board.addLane(id=remote_lane['id'],
                                     position=remote_lane['position'],
                                     created=remote_created)
            else:
                lane = session.getLaneByID(remote_lane['id'])
            lane.updated = parseDateTime(remote_lane['updated_at'])
            t = SyncWorklistTask(remote_lane['worklist']['id'],
                                 priority=self.priority)
            t._run(sync, session, remote_lane['worklist'])
            lane.worklist = session.getWorklistByID(remote_lane['worklist']['id'])
        for local_lane in board.lanes[:]:
            if local_lane.id not in remote_lane_ids:
                session.delete(lane)

    def run(self, sync):
        app = sync.app
        if self.data is None:
            remote_board = sync.get('v1/boards/%s' % (self.board_id,))
        else:
            remote_board = self.data

        with app.db.getSession() as session:
            board = session.getBoardByID(remote_board['id'])
            added = False
            if not board:
                board = session.createBoard(id=remote_board['id'])
                sync.log.info("Created new board %s in local DB.", board.id)
                added = True
            board.title = remote_board['title']
            board.description = remote_board['description']
            board.updated = parseDateTime(remote_board['updated_at'])
            board.creator = getUser(sync, session,
                                    remote_board['creator_id'])
            board.created = parseDateTime(remote_board['created_at'])

            self.updateLanes(sync, session, board, remote_board['lanes'])

            if added:
                self.results.append(BoardAddedEvent(board))
            else:
                self.results.append(BoardUpdatedEvent(board))

class SyncWorklistTask(Task):
    def __init__(self, worklist_id, data=None, priority=NORMAL_PRIORITY):
        super(SyncWorklistTask, self).__init__(priority)
        self.worklist_id = worklist_id
        self.data = data

    def __repr__(self):
        return '<SyncWorklistTask %s>' % (self.worklist_id,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.worklist_id == self.worklist_id and
            other.data == self.data):
            return True
        return False

    def updateItems(self, sync, session, worklist, remote_items):
        local_item_ids = set([l.id for l in worklist.items])
        remote_item_ids = set()
        reenqueue = False
        for remote_item in remote_items:
            remote_item_ids.add(remote_item['id'])
            if remote_item['id'] not in local_item_ids:
                self.log.debug("Adding to worklist id %s item %s" %
                               (worklist.id, remote_item,))
                remote_created = parseDateTime(remote_item['created_at'])
                self.log.debug("Create item %s", remote_item['id'])
                item = worklist.addItem(id=remote_item['id'],
                                        position=remote_item['list_position'],
                                        created=remote_created)
            else:
                self.log.debug("Get item %s", remote_item['id'])
                item = session.getWorklistItemByID(remote_item['id'])
            self.log.debug("Using item %s", item)
            item.updated = parseDateTime(remote_item['updated_at'])
            if remote_item['item_type'] == 'story':
                item.story = session.getStoryByID(remote_item['item_id'])
                self.log.debug("Story %s", item.story)
                if item.story is None:
                    self.tasks.append(sync.submitTask(SyncStoryTask(
                        remote_item['item_id'], priority=self.priority)))
                    reenqueue = True
            if remote_item['item_type'] == 'task':
                item.task = session.getTaskByID(remote_item['item_id'])
                self.log.debug("Task %s", item.task)
                if item.task is None:
                    self.tasks.append(sync.submitTask(SyncStoryByTaskTask(
                        remote_item['item_id'], priority=self.priority)))
                    reenqueue = True
        if reenqueue:
            self.tasks.append(sync.submitTask(SyncWorklistTask(
                self.worklist_id, self.data, priority=self.priority)))

        for local_item in worklist.items[:]:
            if local_item.id not in remote_item_ids:
                session.delete(local_item)

    def run(self, sync):
        app = sync.app
        if self.data is None:
            remote_worklist = sync.get('v1/worklists/%s' % (self.worklist_id,))
        else:
            remote_worklist = self.data

        with app.db.getSession() as session:
            return self._run(sync, session, remote_worklist)

    def _run(self, sync, session, remote_worklist):
        worklist = session.getWorklistByID(remote_worklist['id'])
        added = False
        if not worklist:
            worklist = session.createWorklist(id=remote_worklist['id'])
            sync.log.info("Created new worklist %s in local DB.", worklist.id)
            added = True
        worklist.title = remote_worklist['title']
        worklist.updated = parseDateTime(remote_worklist['updated_at'])
        worklist.creator = getUser(sync, session,
                                remote_worklist['creator_id'])
        worklist.created = parseDateTime(remote_worklist['created_at'])

        self.updateItems(sync, session, worklist, remote_worklist['items'])

        if added:
            self.results.append(WorklistAddedEvent(worklist))
        else:
            self.results.append(WorklistUpdatedEvent(worklist))

#storyboard
class SyncQueriedChangesTask(Task):
    def __init__(self, query_name, query, priority=NORMAL_PRIORITY):
        super(SyncQueriedChangesTask, self).__init__(priority)
        self.query_name = query_name
        self.query = query

    def __repr__(self):
        return '<SyncQueriedChangesTask %s>' % self.query_name

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.query_name == self.query_name and
            other.query == self.query):
            return True
        return False

    def run(self, sync):
        app = sync.app
        now = datetime.datetime.utcnow()
        with app.db.getSession() as session:
            sync_query = session.getSyncQueryByName(self.query_name)
            query = 'q=%s' % self.query
            if sync_query.updated:
                # Allow 4 seconds for request time, etc.
                query += ' -age:%ss' % (int(math.ceil((now-sync_query.updated).total_seconds())) + 4,)
            else:
                query += ' status:open'
            for project in session.getProjects(subscribed=True):
                query += ' -project:%s' % project.name
        changes = []
        sortkey = ''
        done = False
        offset = 0
        while not done:
            # We don't actually want to limit to 500, but that's the server-side default, and
            # if we don't specify this, we won't get a _more_changes flag.
            q = 'changes/?n=500%s&%s' % (sortkey, query)
            self.log.debug('Query: %s ' % (q,))
            batch = sync.get(q)
            done = True
            if batch:
                changes += batch
                if '_more_changes' in batch[-1]:
                    done = False
                    if '_sortkey' in batch[-1]:
                        sortkey = '&N=%s' % (batch[-1]['_sortkey'],)
                    else:
                        offset += len(batch)
                        sortkey = '&start=%s' % (offset,)
        change_ids = [c['id'] for c in changes]
        with app.db.getSession() as session:
            # Winnow the list of IDs to only the ones in the local DB.
            change_ids = session.getChangeIDs(change_ids)

        for c in changes:
            # For now, just sync open changes or changes already
            # in the db optionally we could sync all changes ever
            if c['id'] in change_ids or (c['status'] not in CLOSED_STATUSES):
                sync.submitTask(SyncChangeTask(c['id'], priority=self.priority))
        sync.submitTask(SetSyncQueryUpdatedTask(self.query_name, now, priority=self.priority))

class SetSyncQueryUpdatedTask(Task):
    def __init__(self, query_name, updated, priority=NORMAL_PRIORITY):
        super(SetSyncQueryUpdatedTask, self).__init__(priority)
        self.query_name = query_name
        self.updated = updated

    def __repr__(self):
        return '<SetSyncQueryUpdatedTask %s %s>' % (self.query_name, self.updated)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.query_name == self.query_name and
            other.updated == self.updated):
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            sync_query = session.getSyncQueryByName(self.query_name)
            sync_query.updated = self.updated

#storyboard
class SyncChangeByNumberTask(Task):
    def __init__(self, number, priority=NORMAL_PRIORITY):
        super(SyncChangeByNumberTask, self).__init__(priority)
        self.number = number

    def __repr__(self):
        return '<SyncChangeByNumberTask %s>' % (self.number,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.number == self.number):
            return True
        return False

    def run(self, sync):
        query = '%s' % self.number
        changes = sync.get('changes/?q=%s' % query)
        self.log.debug('Query: %s ' % (query,))
        for c in changes:
            task = SyncChangeTask(c['id'], priority=self.priority)
            self.tasks.append(task)
            sync.submitTask(task)
            self.log.debug("Sync change %s because it is number %s" % (c['id'], self.number))

#storyboard
class SyncOutdatedChangesTask(Task):
    def __init__(self, priority=NORMAL_PRIORITY):
        super(SyncOutdatedChangesTask, self).__init__(priority)

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def __repr__(self):
        return '<SyncOutdatedChangesTask>'

    def run(self, sync):
        with sync.app.db.getSession() as session:
            for change in session.getOutdated():
                self.log.debug("Sync outdated change %s" % (change.id,))
                sync.submitTask(SyncChangeTask(change.id, priority=self.priority))


class UpdateStoriesTask(Task):
    def __repr__(self):
        return '<UpdateStoriesTask>'

    def __eq__(self, other):
        if (other.__class__ == self.__class__):
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            #for c in session.getPendingStarred():
            #    sync.submitTask(ChangeStarredTask(c.key, self.priority))
            for s in session.getPendingStories():
                sync.submitTask(UpdateStoryTask(s.key, self.priority))
            for t in session.getPendingTasks():
                sync.submitTask(UpdateTaskTask(t.key, self.priority))
            #for m in session.getPendingMessages():
            #    sync.submitTask(UploadReviewTask(m.key, self.priority))

#storyboard
class ChangeStarredTask(Task):
    def __init__(self, change_key, priority=NORMAL_PRIORITY):
        super(ChangeStarredTask, self).__init__(priority)
        self.change_key = change_key

    def __repr__(self):
        return '<ChangeStarredTask %s>' % (self.change_key,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.change_key == self.change_key):
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            change = session.getChange(self.change_key)
            if change.starred:
                sync.put('users/self/starred.changes/%s' % (change.id,),
                         data={})
            else:
                sync.delete('users/self/starred.changes/%s' % (change.id,),
                            data={})
            change.pending_starred = False
            sync.submitTask(SyncChangeTask(change.id, priority=self.priority))

class UpdateStoryTask(Task):
    def __init__(self, story_key, priority=NORMAL_PRIORITY):
        super(UpdateStoryTask, self).__init__(priority)
        self.story_key = story_key

    def __repr__(self):
        return '<UpdateStoryTask %s>' % (self.story_key,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.story_key == self.story_key):
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            story = session.getStory(self.story_key)
            data = {}
            #if story.pending_description:
            #    story.pending_description = False
            data['description'] = story.description
            data['title'] = story.title
            tags_data = []
            tags_data = list([t.name for t in story.tags])
            story.pending = False

            if story.id is None:
                result = sync.post('v1/stories', data)
                story.id = result['id']
            else:
                result = sync.put('v1/stories/%s' % (story.id,),
                                  data)
            local_tags = set(tags_data)
            remote_tags = sync.get('v1/stories/%s/tags' % (story.id,))
            remote_tags = set([t['name'] for t in remote_tags])
            added = list(local_tags - remote_tags)
            removed = list(remote_tags - local_tags)
            if removed:
                self.log.info("Remove tags %s from %s",
                              removed, story.id)
                sync.delete('v1/tags/%s' % (story.id,),
                            removed)
            if added:
                self.log.info("Add tags %s to %s",
                              added, story.id)
                result = sync.put('v1/tags/%s' % (story.id,),
                                  added)
        sync.submitTask(SyncStoryTask(story.id,
                                      priority=self.priority))

class UpdateTaskTask(Task):
    def __init__(self, task_key, priority=NORMAL_PRIORITY):
        super(UpdateTaskTask, self).__init__(priority)
        self.task_key = task_key

    def __repr__(self):
        return '<UpdateTaskTask %s>' % (self.task_key,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.task_key == self.task_key):
            return True
        return False

    def run(self, sync):
        # storyboard: hold a story if task is out of date?
        app = sync.app
        with app.db.getSession() as session:
            task = session.getTask(self.task_key)
            if task.pending_delete:
                result = sync.delete('v1/tasks/%s' % (task.id,),
                                     {})
                session.delete(task)
                return
            story_id = task.story.id
            data = {}
            data['assignee_id'] = reference(task.assignee)
            data['project_id'] = reference(task.project)
            data['status'] = task.status
            data['title'] = task.title
            data['story_id'] = reference(task.story)
            data['link'] = task.link
            if task.id:
                result = sync.put('v1/tasks/%s' % (task.id,),
                                   data)
            else:
                result = sync.post('v1/tasks/', data)
                task.id = result['id']
            task.pending = False
        sync.submitTask(SyncStoryTask(story_id,
                                      priority=self.priority))

class AddCommentTask(Task):
    def __init__(self, event_key, priority=NORMAL_PRIORITY):
        super(AddCommentTask, self).__init__(priority)
        self.event_key = event_key

    def __repr__(self):
        return '<AddCommentTask %s>' % (self.event_key,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.event_key == self.event_key):
            return True
        return False

    def run(self, sync):
        app = sync.app

        with app.db.getSession() as session:
            event = session.getEvent(self.event_key)
            data = dict(content=event.comment.content)
            result = sync.post('v1/stories/%s/comments' % (event.story.id,), data)
            session.delete(event)
            sync.submitTask(SyncStoryTask(event.story.id, priority=self.priority))

class PruneDatabaseTask(Task):
    def __init__(self, age, priority=NORMAL_PRIORITY):
        super(PruneDatabaseTask, self).__init__(priority)
        self.age = age

    def __repr__(self):
        return '<PruneDatabaseTask %s>' % (self.age,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.age == self.age):
            return True
        return False

    def run(self, sync):
        if not self.age:
            return
        app = sync.app
        with app.db.getSession() as session:
            for change in session.getChanges('status:closed age:%s' % self.age):
                t = PruneChangeTask(change.key, priority=self.priority)
                self.tasks.append(t)
                sync.submitTask(t)
        t = VacuumDatabaseTask(priority=self.priority)
        self.tasks.append(t)
        sync.submitTask(t)

#storyboard
class PruneChangeTask(Task):
    def __init__(self, key, priority=NORMAL_PRIORITY):
        super(PruneChangeTask, self).__init__(priority)
        self.key = key

    def __repr__(self):
        return '<PruneChangeTask %s>' % (self.key,)

    def __eq__(self, other):
        if (other.__class__ == self.__class__ and
            other.key == self.key):
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            change = session.getChange(self.key)
            if not change:
                return
            repo = gitrepo.get_repo(change.project.name, app.config)
            self.log.info("Pruning %s change %s status:%s updated:%s" % (
                change.project.name, change.number, change.status, change.updated))
            change_ref = None
            for revision in change.revisions:
                if change_ref is None:
                    change_ref = '/'.join(revision.fetch_ref.split('/')[:-1])
                self.log.info("Deleting %s ref %s" % (
                    change.project.name, revision.fetch_ref))
                repo.deleteRef(revision.fetch_ref)
            self.log.info("Deleting %s ref %s" % (
                change.project.name, change_ref))
            try:
                repo.deleteRef(change_ref)
            except OSError as e:
                if e.errno not in [errno.EISDIR, errno.EPERM]:
                    raise
            session.delete(change)

class VacuumDatabaseTask(Task):
    def __init__(self, priority=NORMAL_PRIORITY):
        super(VacuumDatabaseTask, self).__init__(priority)

    def __repr__(self):
        return '<VacuumDatabaseTask>'

    def __eq__(self, other):
        if other.__class__ == self.__class__:
            return True
        return False

    def run(self, sync):
        app = sync.app
        with app.db.getSession() as session:
            session.vacuum()

class Sync(object):
    def __init__(self, app, disable_background_sync):
        self.user_agent = 'Boartty/%s %s' % (boartty.version.version_info.release_string(),
                                            requests.utils.default_user_agent())
        self.version = (0, 0, 0)
        self.offline = False
        self.app = app
        self.log = logging.getLogger('boartty.sync')
        self.queue = MultiQueue([HIGH_PRIORITY, NORMAL_PRIORITY, LOW_PRIORITY])
        self.result_queue = queue.Queue()
        self.session = requests.Session()
        self.token = 'Bearer %s' % (self.app.config.token)
        self.submitTask(GetVersionTask(HIGH_PRIORITY))
        self.submitTask(SyncOwnUserTask(HIGH_PRIORITY))
        if not disable_background_sync:
            self.submitTask(UpdateStoriesTask(HIGH_PRIORITY))
            self.submitTask(SyncProjectListTask(HIGH_PRIORITY))
            self.submitTask(SyncUserListTask(HIGH_PRIORITY))
            self.submitTask(SyncProjectSubscriptionsTask(NORMAL_PRIORITY))
            self.submitTask(SyncSubscribedProjectsTask(NORMAL_PRIORITY))
            self.submitTask(SyncBoardsTask(NORMAL_PRIORITY))
            self.submitTask(SyncWorklistsTask(NORMAL_PRIORITY))
            #self.submitTask(SyncSubscribedProjectBranchesTask(LOW_PRIORITY))
            #self.submitTask(SyncOutdatedChangesTask(LOW_PRIORITY))
            #self.submitTask(PruneDatabaseTask(self.app.config.expire_age, LOW_PRIORITY))
            self.periodic_thread = threading.Thread(target=self.periodicSync)
            self.periodic_thread.daemon = True
            self.periodic_thread.start()

    def periodicSync(self):
        hourly = time.time()
        while True:
            try:
                time.sleep(60)
                self.syncSubscribedProjects()
                now = time.time()
                if now-hourly > 3600:
                    hourly = now
                    #self.pruneDatabase()
                    #self.syncOutdatedChanges()
            except Exception:
                self.log.exception('Exception in periodicSync')

    def submitTask(self, task):
        self.log.debug("Enqueue %s", task)
        if not self.offline:
            if not self.queue.put(task, task.priority):
                task.complete(False)
        else:
            task.complete(False)
        return task

    def run(self, pipe):
        task = None
        while True:
            task = self._run(pipe, task)

    def _run(self, pipe, task=None):
        if not task:
            task = self.queue.get()
        self.log.debug('Run: %s' % (task,))
        try:
            task.run(self)
            task.complete(True)
            self.queue.complete(task)
        except (requests.ConnectionError, OfflineError) as e:
            self.log.warning("Offline due to: %s" % (e,))
            if not self.offline:
                self.submitTask(GetVersionTask(HIGH_PRIORITY))
                #storyboard:
                #self.submitTask(UploadReviewsTask(HIGH_PRIORITY))
            self.offline = True
            self.app.status.update(offline=True, refresh=False)
            os.write(pipe, six.b('refresh\n'))
            time.sleep(30)
            return task
        except Exception:
            task.complete(False)
            self.queue.complete(task)
            self.log.exception('Exception running task %s' % (task,))
            self.app.status.update(error=True, refresh=False)
        self.offline = False
        self.app.status.update(offline=False, refresh=False)
        for r in task.results:
            self.result_queue.put(r)
        os.write(pipe, six.b('refresh\n'))
        return None

    def url(self, path):
        return self.app.config.url + 'api/' + path

    def checkResponse(self, response):
        self.log.debug('HTTP status code: %d', response.status_code)
        self.log.debug(response.text[:255])
        if response.status_code == 503:
            raise OfflineError("Received 503 status code")

    def get(self, path):
        url = self.url(path)
        self.log.debug('GET: %s' % (url,))

        r = self.session.get(url,
                             verify=self.app.config.verify_ssl,
                             timeout=TIMEOUT,
                             headers = {'Accept': 'application/json',
                                        'Accept-Encoding': 'gzip',
                                        'User-Agent': self.user_agent,
                                        'Authorization': self.token})

        self.checkResponse(r)
        if r.status_code == 200:
            ret = json.loads(r.text)
            if len(ret):
                self.log.debug('200 OK')
            else:
                self.log.debug('200 OK, No body.')
            return ret

    def post(self, path, data):
        url = self.url(path)
        self.log.debug('POST: %s' % (url,))
        self.log.debug('data: %s' % (data,))
        r = self.session.post(url, data=json.dumps(data).encode('utf8'),
                              verify=self.app.config.verify_ssl,
                              timeout=TIMEOUT,
                              headers = {'Content-Type': 'application/json;charset=UTF-8',
                                         'User-Agent': self.user_agent,
                                         'Authorization': self.token})
        self.checkResponse(r)
        self.log.debug('Received: %s' % (r.text,))
        ret = None
        if r.text:
            try:
                ret = json.loads(r.text)
            except Exception:
                self.log.exception("Unable to parse result %s from post to %s" %
                                   (r.text, url))
        return ret

    def put(self, path, data):
        url = self.url(path)
        self.log.debug('PUT: %s' % (url,))
        self.log.debug('data: %s' % (data,))
        r = self.session.put(url, data=json.dumps(data).encode('utf8'),
                             verify=self.app.config.verify_ssl,
                             timeout=TIMEOUT,
                             headers = {'Content-Type': 'application/json;charset=UTF-8',
                                        'User-Agent': self.user_agent,
                                        'Authorization': self.token})
        self.checkResponse(r)
        self.log.debug('Received: %s' % (r.text,))
        if r.status_code == 200:
            ret = json.loads(r.text)
            if len(ret):
                self.log.debug('200 OK')
            else:
                self.log.debug('200 OK, No body.')
            return ret

    def delete(self, path, data):
        url = self.url(path)
        self.log.debug('DELETE: %s' % (url,))
        self.log.debug('data: %s' % (data,))
        r = self.session.delete(url, data=json.dumps(data).encode('utf8'),
                                verify=self.app.config.verify_ssl,
                                timeout=TIMEOUT,
                                headers = {'Content-Type': 'application/json;charset=UTF-8',
                                           'User-Agent': self.user_agent,
                                           'Authorization': self.token})
        self.checkResponse(r)
        self.log.debug('Received: %s' % (r.text,))

    def syncSubscribedProjects(self):
        task = SyncSubscribedProjectsTask(LOW_PRIORITY)
        self.submitTask(task)
        if task.wait():
            for subtask in task.tasks:
                subtask.wait()

    def pruneDatabase(self):
        task = PruneDatabaseTask(self.app.config.expire_age, LOW_PRIORITY)
        self.submitTask(task)
        if task.wait():
            for subtask in task.tasks:
                subtask.wait()

    def syncOutdatedChanges(self):
        task = SyncOutdatedChangesTask(LOW_PRIORITY)
        self.submitTask(task)
        if task.wait():
            for subtask in task.tasks:
                subtask.wait()

    def setRemoteVersion(self, version):
        base = version.split('-')[0]
        parts = base.split('.')
        major = minor = micro = 0
        if len(parts) > 0:
            major = int(parts[0])
        if len(parts) > 1:
            minor = int(parts[1])
        if len(parts) > 2:
            micro = int(parts[2])
        self.version = (major, minor, micro)
        self.log.info("Remote version is: %s (parsed as %s)" % (version, self.version))
