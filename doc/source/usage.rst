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
~~~~~~~~~~~~~~~~~~~~

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

You will want to adjust the pattern to match the Storyboard site you are
interested in; multiple patterns may be added as needed.
