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
import re
import time
import logging
import threading

import alembic
import alembic.config
import six
import sqlalchemy
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.schema import ForeignKey
from sqlalchemy.orm import mapper, sessionmaker, relationship, scoped_session, joinedload
from sqlalchemy.orm.session import Session
from sqlalchemy.sql import exists
from sqlalchemy.sql.expression import and_

metadata = MetaData()
system_table = Table(
    'system', metadata,
    Column('key', Integer, primary_key=True),
    Column('user_id', Integer),
    )
project_table = Table(
    'project', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('name', String(255), index=True, nullable=False),
    Column('subscribed', Boolean, index=True, default=False),
    Column('description', Text),
    Column('updated', DateTime, index=True),
    )
topic_table = Table(
    'topic', metadata,
    Column('key', Integer, primary_key=True),
    Column('name', String(255), index=True, nullable=False),
    Column('sequence', Integer, index=True, unique=True, nullable=False),
    )
project_topic_table = Table(
    'project_topic', metadata,
    Column('key', Integer, primary_key=True),
    Column('project_key', Integer, ForeignKey("project.key"), index=True),
    Column('topic_key', Integer, ForeignKey("topic.key"), index=True),
    Column('sequence', Integer, nullable=False),
    UniqueConstraint('topic_key', 'sequence', name='topic_key_sequence_const'),
    )
story_table = Table(
    'story', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('user_key', Integer, ForeignKey("user.key"), index=True),
    Column('status', String(16), index=True, nullable=False),
    Column('hidden', Boolean, index=True, nullable=False),
    Column('subscribed', Boolean, index=True, nullable=False),
    Column('title', String(255), index=True),
    Column('private', Boolean, nullable=False),
    Column('description', Text),
    Column('created', DateTime, index=True),
    # TODO: make sure updated is never null in storyboard
    Column('updated', DateTime, index=True),
    Column('last_seen', DateTime, index=True),
    Column('outdated', Boolean, index=True, nullable=False),
    Column('pending', Boolean, index=True, nullable=False),
    Column('pending_delete', Boolean, index=True, nullable=False),
)
board_table = Table(
    'board', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('user_key', Integer, ForeignKey("user.key"), index=True),
    Column('hidden', Boolean, index=True, nullable=False, default=False),
    Column('subscribed', Boolean, index=True, nullable=False, default=False),
    Column('title', String(255), index=True),
    Column('private', Boolean, nullable=False, default=False),
    Column('description', Text),
    Column('created', DateTime, index=True),
    Column('updated', DateTime, index=True),
    Column('last_seen', DateTime, index=True),
    Column('pending', Boolean, index=True, nullable=False, default=False),
    Column('pending_delete', Boolean, index=True, nullable=False, default=False),
)
lane_table = Table(
    'lane', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('board_key', Integer, ForeignKey("board.key"), index=True),
    Column('worklist_key', Integer, ForeignKey("worklist.key"), index=True),
    Column('position', Integer),
    Column('created', DateTime, index=True),
    Column('updated', DateTime, index=True),
    Column('pending', Boolean, index=True, nullable=False, default=False),
    Column('pending_delete', Boolean, index=True, nullable=False, default=False),
)
worklist_table = Table(
    'worklist', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('user_key', Integer, ForeignKey("user.key"), index=True),
    Column('hidden', Boolean, index=True, nullable=False, default=False),
    Column('subscribed', Boolean, index=True, nullable=False, default=False),
    Column('title', String(255), index=True),
    Column('private', Boolean, nullable=False, default=False),
    Column('automatic', Boolean, nullable=False, default=False),
    Column('created', DateTime, index=True),
    Column('updated', DateTime, index=True),
    Column('last_seen', DateTime, index=True),
    Column('pending', Boolean, index=True, nullable=False, default=False),
    Column('pending_delete', Boolean, index=True, nullable=False, default=False),
)
worklist_item_table = Table(
    'worklist_item', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('worklist_key', Integer, ForeignKey("worklist.key"), index=True),
    Column('story_key', Integer, ForeignKey("story.key"), index=True),
    Column('task_key', Integer, ForeignKey("task.key"), index=True),
    Column('position', Integer),
    Column('created', DateTime, index=True),
    Column('updated', DateTime, index=True),
    Column('pending', Boolean, index=True, nullable=False, default=False),
    Column('pending_delete', Boolean, index=True, nullable=False, default=False),
)
tag_table = Table(
    'tag', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('name', String(255), index=True, nullable=False),
)
story_tag_table = Table(
    'story_tag', metadata,
    Column('key', Integer, primary_key=True),
    Column('story_key', Integer, ForeignKey("story.key"), index=True),
    Column('tag_key', Integer, ForeignKey("tag.key"), index=True),
    UniqueConstraint('story_key', 'tag_key', name='story_tag_unique'),
)
task_table = Table(
    'task', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('title', String(255), index=True),
    Column('status', String(16), index=True),
    Column('creator_user_key', Integer, ForeignKey("user.key"), index=True),
    Column('story_key', Integer, ForeignKey("story.key"), index=True),
    Column('project_key', Integer, ForeignKey("project.key"), index=True),
    Column('assignee_user_key', Integer, ForeignKey("user.key"), index=True),
    Column('priority', String(16)),
    Column('link', Text),
    Column('created', DateTime, index=True),
    # TODO: make sure updated is never null in storyboard
    Column('updated', DateTime, index=True),
    Column('pending', Boolean, index=True, nullable=False),
    Column('pending_delete', Boolean, index=True, nullable=False),
)
event_table = Table(
    'event', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('type', String(255), index=True, nullable=False),
    Column('user_key', Integer, ForeignKey("user.key"), index=True),
    Column('story_key', Integer, ForeignKey('story.key'), nullable=True),
    #Column('worklist_key', Integer, ForeignKey('worklist.key'), nullable=True),
    #Column('board_key', Integer, ForeignKey('board.key'), nullable=True),
    Column('created', DateTime, index=True),
    Column('comment_key', Integer, ForeignKey('comment.key'), nullable=True),
    Column('user_key', ForeignKey('user.key'), nullable=True),
    Column('info', Text),
)
comment_table = Table(
    'comment', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('parent_comment_key', Integer, ForeignKey('comment.key'), nullable=True),
    Column('content', Text),
    Column('draft', Boolean, index=True, nullable=False),
    Column('pending', Boolean, index=True, nullable=False),
    Column('pending_delete', Boolean, index=True, nullable=False),
)
user_table = Table(
    'user', metadata,
    Column('key', Integer, primary_key=True),
    Column('id', Integer, index=True),
    Column('name', String(255), index=True),
    Column('email', String(255), index=True),
    )
sync_query_table = Table(
    'sync_query', metadata,
    Column('key', Integer, primary_key=True),
    Column('name', String(255), index=True, unique=True, nullable=False),
    Column('updated', DateTime, index=True),
    )

class System(object):
    def __init__(self, user_id=None):
        self.user_id = user_id

class User(object):
    def __init__(self, id, name=None, email=None):
        self.id = id
        self.name = name
        self.email = email

class Project(object):
    def __init__(self, id, name, subscribed=False, description=''):
        self.id = id
        self.name = name
        self.subscribed = subscribed
        self.description = description

    def createChange(self, *args, **kw):
        session = Session.object_session(self)
        args = [self] + list(args)
        c = Change(*args, **kw)
        self.changes.append(c)
        session.add(c)
        session.flush()
        return c

    def createBranch(self, *args, **kw):
        session = Session.object_session(self)
        args = [self] + list(args)
        b = Branch(*args, **kw)
        self.branches.append(b)
        session.add(b)
        session.flush()
        return b

class ProjectTopic(object):
    def __init__(self, project, topic, sequence):
        self.project_key = project.key
        self.topic_key = topic.key
        self.sequence = sequence

class Topic(object):
    def __init__(self, name, sequence):
        self.name = name
        self.sequence = sequence

    def addProject(self, project):
        session = Session.object_session(self)
        seq = max([x.sequence for x in self.project_topics] + [0])
        pt = ProjectTopic(project, self, seq+1)
        self.project_topics.append(pt)
        self.projects.append(project)
        session.add(pt)
        session.flush()

    def removeProject(self, project):
        session = Session.object_session(self)
        for pt in self.project_topics:
            if pt.project_key == project.key:
                self.project_topics.remove(pt)
                session.delete(pt)
        self.projects.remove(project)
        session.flush()

def format_name(self):
    name = 'Anonymous Coward'
    if self.creator:
        if self.creator.name:
            name = self.creator.name
        elif self.creator.email:
            name = self.creator.email
    return name

class Story(object):
    def __init__(self, id=None, creator=None, created=None, title=None,
                 description=None, pending=False):
        self.id = id
        self.creator = creator
        self.title = title
        self.description = description
        self.status = 'active'
        self.created = created
        self.private = False
        self.outdated = False
        self.hidden = False
        self.subscribed = False
        self.pending = pending
        self.pending_delete = False

    def __repr__(self):
        return '<Story key=%s id=%s title=%s>' % (
            self.key, self.id, self.title)

    @property
    def creator_name(self):
        return format_name(self)

    def addEvent(self, *args, **kw):
        session = Session.object_session(self)
        e = Event(*args, **kw)
        e.story_key = self.key
        self.events.append(e)
        session.add(e)
        session.flush()
        return e

    def addTask(self, *args, **kw):
        session = Session.object_session(self)
        t = Task(*args, **kw)
        t.story_key = self.key
        self.tasks.append(t)
        session.add(t)
        session.flush()
        return t

    def getDraftCommentEvent(self, parent):
        for event in self.events:
            if (event.comment and event.comment.draft and
                event.comment.parent==parent):
                return event
        return None

    def setDraftComment(self, creator, parent, content):
        event = self.getDraftCommentEvent(parent)
        if event is None:
            event = self.addEvent(type='user_comment', creator=creator)
            event.addComment()
        event.comment.content = content
        event.comment.draft = True
        event.comment.parent = parent
        return event

class Tag(object):
    def __init__(self, id, name):
        self.id = id
        self.name = name

class StoryTag(object):
    def __init__(self, story, tag):
        self.story_key = story.key
        self.tag_key = tag.key

class Task(object):
    def __init__(self, id=None, title=None, status=None, creator=None,
                 created=None, pending=False, pending_delete=False,
                 project=None):
        self.id = id
        self.title = title
        self.status = status
        self.pending = pending
        self.pending_delete = pending_delete
        self.creator = creator
        self.created = created
        self.project = project

    def __repr__(self):
        return '<Task key=%s id=%s title=%s, project=%s>' % (
            self.key, self.id, self.title, self.project)

class Event(object):
    def __init__(self, id=None, type=None, creator=None, created=None, info=None):
        self.id = id
        self.type = type
        self.creator = creator
        if created is None:
            created = datetime.datetime.utcnow()
        self.created = created
        self.info = info

    @property
    def creator_name(self):
        return format_name(self)

    @property
    def description(self):
        return re.sub('_', ' ', self.type)

    def addComment(self, *args, **kw):
        session = Session.object_session(self)
        c = Comment(*args, **kw)
        session.add(c)
        session.flush()
        self.comment_key = c.key
        return c

class Comment(object):
    def __init__(self, id=None, content=None, parent=None, draft=False,
                 pending=False, pending_delete=False):
        self.id = id
        self.content = content
        self.parent = parent
        self.pending = pending
        self.pending_delete = pending_delete
        self.draft = draft

class Board(object):
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __repr__(self):
        return '<Board key=%s id=%s title=%s>' % (
            self.key, self.id, self.title)

    def addLane(self, *args, **kw):
        session = Session.object_session(self)
        l = Lane(*args, **kw)
        session.add(l)
        session.flush()
        l.board = self
        return l

class Lane(object):
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __repr__(self):
        return '<Lane key=%s id=%s worklist=%s>' % (
            self.key, self.id, self.worklist)

class Worklist(object):
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __repr__(self):
        return '<Worklist key=%s id=%s title=%s>' % (
            self.key, self.id, self.title)

    def addItem(self, *args, **kw):
        session = Session.object_session(self)
        i = WorklistItem(*args, **kw)
        session.add(i)
        session.flush()
        i.worklist = self
        return i

class WorklistItem(object):
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __repr__(self):
        return '<WorklistItem key=%s id=%s story=%s task=%s>' % (
            self.key, self.id, self.story, self.task)

    @property
    def title(self):
        if self.story:
            return self.story.title
        elif self.task:
            return self.task.title
        return 'Unknown'

    @property
    def dereferenced_story_key(self):
        if self.story:
            return self.story.key
        elif self.task:
            return self.task.story.key
        return None

class SyncQuery(object):
    def __init__(self, name):
        self.name = name

mapper(System, system_table)
mapper(User, user_table)
mapper(Project, project_table, properties=dict(
    topics=relationship(Topic,
                        secondary=project_topic_table,
                        order_by=topic_table.c.name,
                        viewonly=True),
    active_stories=relationship(Story,
                                secondary=task_table,
                                primaryjoin=and_(project_table.c.key==task_table.c.project_key,
                                                 story_table.c.key==task_table.c.story_key,
                                                 story_table.c.status=='active'),
                                order_by=story_table.c.id,
                            ),
    stories=relationship(Story,
                         secondary=task_table,
                         order_by=story_table.c.id,
                     ),
))
mapper(Topic, topic_table, properties=dict(
    projects=relationship(Project,
                          secondary=project_topic_table,
                          order_by=project_table.c.name,
                          viewonly=True),
    project_topics=relationship(ProjectTopic),
))
mapper(ProjectTopic, project_topic_table)
mapper(Story, story_table, properties=dict(
        creator=relationship(User),
        tags=relationship(Tag,
                          secondary=story_tag_table,
                          order_by=tag_table.c.name,
                          #viewonly=True
                          ),
        tasks=relationship(Task, backref='story',
                           cascade='all, delete-orphan'),
        events=relationship(Event, backref='story',
                            cascade='all, delete-orphan'),
))
mapper(Tag, tag_table)
mapper(StoryTag, story_tag_table)
mapper(Task, task_table, properties=dict(
    project=relationship(Project),
    assignee=relationship(User, foreign_keys=task_table.c.assignee_user_key),
    creator=relationship(User, foreign_keys=task_table.c.creator_user_key),
))
mapper(Event, event_table, properties=dict(
    creator=relationship(User),
    comment=relationship(Comment, backref='event'),
))
mapper(Comment, comment_table, properties=dict(
    parent=relationship(Comment, remote_side=[comment_table.c.key],backref='children'),
))
mapper(Board, board_table, properties=dict(
    lanes=relationship(Lane,
                       order_by=lane_table.c.position),
    creator=relationship(User),
))
mapper(Lane, lane_table, properties=dict(
    board=relationship(Board),
    worklist=relationship(Worklist),
))
mapper(Worklist, worklist_table, properties=dict(
    items=relationship(WorklistItem,
                       order_by=worklist_item_table.c.position),
    creator=relationship(User),
))
mapper(WorklistItem, worklist_item_table, properties=dict(
    worklist=relationship(Worklist),
    story=relationship(Story),
    task=relationship(Task),
))
mapper(SyncQuery, sync_query_table)

def match(expr, item):
    if item is None:
        return False
    return re.match(expr, item) is not None

@sqlalchemy.event.listens_for(sqlalchemy.engine.Engine, "connect")
def add_sqlite_match(dbapi_connection, connection_record):
    dbapi_connection.create_function("matches", 2, match)

class Database(object):
    def __init__(self, app, dburi, search):
        self.log = logging.getLogger('boartty.db')
        self.dburi = dburi
        self.search = search
        self.engine = create_engine(self.dburi)
        metadata.create_all(self.engine)
        self.migrate(app)
        # If we want the objects returned from query() to be usable
        # outside of the session, we need to expunge them from the session,
        # and since the DatabaseSession always calls commit() on the session
        # when the context manager exits, we need to inform the session to
        # expire objects when it does so.
        self.session_factory = sessionmaker(bind=self.engine,
                                            expire_on_commit=False,
                                            autoflush=False)
        self.session = scoped_session(self.session_factory)
        self.lock = threading.Lock()

    def getSession(self):
        return DatabaseSession(self)

    def migrate(self, app):
        conn = self.engine.connect()
        context = alembic.migration.MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        self.log.debug('Current migration revision: %s' % current_rev)

        has_table = self.engine.dialect.has_table(conn, "project")

        config = alembic.config.Config()
        config.set_main_option("script_location", "boartty:alembic")
        config.set_main_option("sqlalchemy.url", self.dburi)
        config.boartty_app = app

        if current_rev is None and has_table:
            self.log.debug('Stamping database as initial revision')
            alembic.command.stamp(config, "183755ac91df")
        alembic.command.upgrade(config, 'head')

class DatabaseSession(object):
    def __init__(self, database):
        self.database = database
        self.session = database.session
        self.search = database.search

    def __enter__(self):
        self.database.lock.acquire()
        self.start = time.time()
        return self

    def __exit__(self, etype, value, tb):
        if etype:
            self.session().rollback()
        else:
            self.session().commit()
        self.session().close()
        self.session = None
        end = time.time()
        self.database.log.debug("Database lock held %s seconds" % (end-self.start,))
        self.database.lock.release()

    def abort(self):
        self.session().rollback()

    def commit(self):
        self.session().commit()

    def delete(self, obj):
        self.session().delete(obj)

    def vacuum(self):
        self.session().execute("VACUUM")

    def getProjects(self, subscribed=False, active=False, topicless=False):
        """Retrieve projects.

        :param subscribed: If True limit to only subscribed projects.
        :param active: If True limit to only projects with active
            stories.
        :param topicless: If True limit to only projects without topics.
        """
        query = self.session().query(Project)
        if subscribed:
            query = query.filter_by(subscribed=subscribed)
            if active:
                query = query.filter(exists().where(Project.active_stories))
        if topicless:
            query = query.filter_by(topics=None)
        return query.order_by(Project.name).all()

    def getTopics(self):
        return self.session().query(Topic).order_by(Topic.sequence).all()

    def getProject(self, key):
        try:
            return self.session().query(Project).filter_by(key=key).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getProjectByName(self, name):
        try:
            return self.session().query(Project).filter_by(name=name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getProjectByID(self, id):
        try:
            return self.session().query(Project).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getTopic(self, key):
        try:
            return self.session().query(Topic).filter_by(key=key).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getTopicByName(self, name):
        try:
            return self.session().query(Topic).filter_by(name=name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getSyncQueryByName(self, name):
        try:
            return self.session().query(SyncQuery).filter_by(name=name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return self.createSyncQuery(name)

    def getStory(self, key):
        query = self.session().query(Story).filter_by(key=key)
        try:
            return query.one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getStoryByID(self, id):
        try:
            return self.session().query(Story).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getStories(self, query, active, sort_by='number'):
        self.database.log.debug("Search query: %s sort: %s" % (query, sort_by))
        q = self.session().query(Story)
        if query:
            q = q.filter(self.search.parse(query))
        if active:
            q = q.filter(story_table.c.hidden==False, story_table.c.status=='active')
        if sort_by == 'updated':
            q = q.order_by(story_table.c.updated)
        elif sort_by == 'last-seen':
            q = q.order_by(story_table.c.last_seen)
        else:
            q = q.order_by(story_table.c.id)
        self.database.log.debug("Search SQL: %s" % q)
        try:
            return q.all()
        except sqlalchemy.orm.exc.NoResultFound:
            return []

    def getTag(self, name):
        try:
            return self.session().query(Tag).filter_by(name=name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getTagByID(self, id):
        try:
            return self.session().query(Tag).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getStoryTag(self, story_key, tag_key):
        try:
            return self.session().query(StoryTag).filter_by(
                story_key=story_key, tag_key=tag_key).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getTask(self, key):
        try:
            return self.session().query(Task).filter_by(key=key).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getTaskByID(self, id):
        try:
            return self.session().query(Task).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getComment(self, key):
        try:
            return self.session().query(Comment).filter_by(key=key).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getCommentByID(self, id):
        try:
            return self.session().query(Comment).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getHeld(self):
        return self.session().query(Story).filter_by(held=True).all()

    def getOutdated(self):
        return self.session().query(Story).filter_by(outdated=True).all()

    def getPendingStories(self):
        return self.session().query(Story).filter_by(pending=True).all()

    def getPendingTasks(self):
        return self.session().query(Task).filter_by(pending=True).all()

    def getUsers(self):
        return self.session().query(User).all()

    def getUser(self, key):
        try:
            return self.session().query(User).filter_by(key=key).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getUserByID(self, id):
        try:
            return self.session().query(User).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getSystem(self):
        try:
            return self.session().query(System).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getEvent(self, key):
        try:
            return self.session().query(Event).filter_by(key=key).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getBoards(self, subscribed=False):
        query = self.session().query(Board)
        if subscribed:
            query = query.filter_by(subscribed=subscribed)
        return query.order_by(Board.title).all()

    def getBoard(self, key):
        query = self.session().query(Board).filter_by(key=key)
        try:
            return query.one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getBoardByID(self, id):
        try:
            return self.session().query(Board).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getLane(self, key):
        query = self.session().query(Lane).filter_by(key=key)
        try:
            return query.one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getLaneByID(self, id):
        try:
            return self.session().query(Lane).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getWorklist(self, key):
        query = self.session().query(Worklist).filter_by(key=key)
        try:
            return query.one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getWorklistByID(self, id):
        try:
            return self.session().query(Worklist).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getWorklistItem(self, key):
        query = self.session().query(WorklistItem).filter_by(key=key)
        try:
            return query.one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def getWorklistItemByID(self, id):
        try:
            return self.session().query(WorklistItem).filter_by(id=id).one()
        except sqlalchemy.orm.exc.NoResultFound:
            return None

    def createProject(self, *args, **kw):
        o = Project(*args, **kw)
        self.session().add(o)
        self.session().flush()
        return o

    def createStory(self, *args, **kw):
        s = Story(*args, **kw)
        self.session().add(s)
        self.session().flush()
        return s

    def createBoard(self, *args, **kw):
        s = Board(*args, **kw)
        self.session().add(s)
        self.session().flush()
        return s

    def createWorklist(self, *args, **kw):
        s = Worklist(*args, **kw)
        self.session().add(s)
        self.session().flush()
        return s

    def createUser(self, *args, **kw):
        a = User(*args, **kw)
        self.session().add(a)
        self.session().flush()
        return a

    def createSyncQuery(self, *args, **kw):
        o = SyncQuery(*args, **kw)
        self.session().add(o)
        self.session().flush()
        return o

    def createTopic(self, *args, **kw):
        o = Topic(*args, **kw)
        self.session().add(o)
        self.session().flush()
        return o

    def createTag(self, *args, **kw):
        o = Tag(*args, **kw)
        self.session().add(o)
        self.session().flush()
        return o

    def createStoryTag(self, *args, **kw):
        o = StoryTag(*args, **kw)
        self.session().add(o)
        self.session().flush()
        return o

    def createSystem(self, *args, **kw):
        o = System(*args, **kw)
        self.session().add(o)
        self.session().flush()
        return o

