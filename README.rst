Boartty
=======

Boartty is a console-based interface to the Storyboard task-tracking
system.

As compared to the web interface, the main advantages are:

 * Workflow -- the interface is designed to support a workflow similar
   to reading network news or mail.  In particular, it is designed to
   deal with a large number of stories across a large number of
   projects.

 * Offline Use -- Boartty syncs information about changes in
   subscribed projects to a local database.  All review operations are
   performed against that database and then synced back to Storyboard.

 * Speed -- user actions modify locally cached content and need not
   wait for server interaction.

Installation
------------

Source
~~~~~~

When installing from source, it is recommended (but not required) to
install Boartty in a virtualenv.  To set one up::

  virtualenv boartty-env
  source boartty-env/bin/activate

To install the latest version from the cheeseshop::

  pip install boartty

To install from a git checkout::

  pip install .

Boartty uses a YAML based configuration file that it looks for at
``~/.boartty.yaml``.  Several sample configuration files are included.
You can find them in the examples/ directory of the
`source distribution <https://git.openstack.org/cgit/openstack/boartty/tree/examples>`_
or the share/boartty/examples directory after installation.

Select one of the sample config files, copy it to ~/.boartty.yaml and
edit as necessary.  Search for ``CHANGEME`` to find parameters that
need to be supplied.  The sample config files are as follows:

**minimal-boartty.yaml**
  Only contains the parameters required for Boartty to actually run.

**reference-boartty.yaml**
  An exhaustive list of all supported options with examples.

**openstack-boartty.yaml**
  A configuration designed for use with OpenStack's installation of
  Storyboard.

You will need a Storyboard authentication token which you can generate
or retrieve by navigating to ``Profile``, then ``Tokens`` (the "key"
icon), or visiting the `/#!/profile/tokens` URI in your Storyboard
installation.  Issue a new token if you have not done so before, and
give it a sufficiently long lifetime (for example, one decade).  Copy
and paste the resulting token in your ``~/.boartty.yaml`` file.

The config file is designed to support multiple Storyboard instances.
The first one is used by default, but others can be specified by
supplying the name on the command line.

Usage
-----

After installing Boartty, you should be able to run it by invoking
``boartty``.  If you installed it in a virtualenv, you can invoke it
without activating the virtualenv with ``/path/to/venv/bin/boartty``
which you may wish to add to your shell aliases.  Use ``boartty
--help`` to see a list of command line options available.

Once Boartty is running, you will need to start by subscribing to some
projects.  Use 'L' to list all of the projects and then 's' to
subscribe to the ones you are interested in.  Hit 'L' again to shrink
the list to your subscribed projects.

In general, pressing the F1 key will show help text on any screen, and
ESC will take you to the previous screen.

Boartty works seamlessly offline or online.  All of the actions that
it performs are first recorded in a local database (in
``~/.boartty.db`` by default), and are then transmitted to Storyboard.
If Boartty is unable to contact Storyboard for any reason, it will
continue to operate against the local database, and once it
re-establishes contact, it will process any pending changes.

The status bar at the top of the screen displays the current number of
outstanding tasks that Boartty must perform in order to be fully up to
date.  Some of these tasks are more complicated than others, and some
of them will end up creating new tasks (for instance, one task may be
to search for new stories in a project which will then produce 5 new
tasks if there are 5 new stories).

If Boartty is offline, it will so indicate in the status bar.  It will
retry requests if needed, and will switch between offline and online
mode automatically.

If Boartty encounters an error, this will also be indicated in the
status bar.  You may wish to examine ~/.boartty.log to see what the
error was.  In many cases, Boartty can continue after encountering an
error.  The error flag will be cleared when you leave the current
screen.

To select text (e.g., to copy to the clipboard), hold Shift while
selecting the text.

Terminal Integration
--------------------

If you use rxvt-unicode, you can add something like the following to
``.Xresources`` to make Storyboard URLs that are displayed in your
terminal (perhaps in an email or irc client) clickable links that open
in Boartty::

  URxvt.perl-ext:           default,matcher
  URxvt.url-launcher:       sensible-browser
  URxvt.keysym.C-Delete:    perl:matcher:last
  URxvt.keysym.M-Delete:    perl:matcher:list
  URxvt.matcher.button:     1
  URxvt.matcher.pattern.1:  https:\/\/storyboard.example.org/#!/story/(\\d+)[\w]*
  URxvt.matcher.launcher.1: boartty --open $0

You will want to adjust the pattern to match the Storyboard site you
are interested in; multiple patterns may be added as needed.

Contributing
------------

For information on how to contribute to Boartty, please see the
contents of the CONTRIBUTING.rst file.

Bugs
----

Bugs are handled at: https://storyboard.openstack.org/
