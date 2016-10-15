Configuration
-------------

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
  Gerrit.

You will need a Storyboard authentication token which you can generate
or retrieve by navigating to ``Profile``, then ``Tokens`` (the "key"
icon), or visiting the `/#!/profile/tokens` URI in your Storyboard
installation.  Issue a new token if you have not done so before, and
give it a sufficiently long lifetime (for example, one decade).  Copy
and paste the resulting token in your ``~/.boartty.yaml`` file.

The config file is designed to support multiple Storyboard instances.
The first one is used by default, but others can be specified by
supplying the name on the command line.

Configuration Reference
~~~~~~~~~~~~~~~~~~~~~~~

The following describes the values that may be set in the
configuration file.

Servers
+++++++

This section lists the servers that Boartty can talk to.  Multiple
servers may be listed; by default, Boartty will use the first one
listed.  To select another, simply specify its name on the command
line.

**servers**
  A list of server definitions.  The format of each entry is described
  below.

  **name (required)**
    A name that describes the server, to reference on the command
    line.

  **url (required)**
    The URL of the Gerrit server.  HTTPS should be preferred.

  **token (required)**
    Your authentication token from Storyboard.  Obtain it as described
    above in "Configuration".

  **dburi**
    The location of Boartty's sqlite database.  If you have more than
    one server, you should specify a dburi for any additional servers.
    By default a SQLite database called ~/.boartty.db is used.

  **ssl-ca-path**
    If your Storyboard server uses a non-standard certificate chain
    (e.g. on a test server), you can pass a full path to a bundle of
    CA certificates here:

  **verify-ssl**
    In case you do not care about security and want to use a
    sledgehammer approach to SSL, you can set this value to false to
    turn off certificate validation.

  **log-file**
    By default Boartty logs errors to a file and truncates that file
    each time it starts (so that it does not grow without bound).  If
    you would like to log to a different location, you may specify it
    with this option.

  **socket**
    Boartty listens on a unix domain socket for remote commands at
    ~/.boartty.sock.  This option may be used to change the path.

  **lock-file**
    Boartty uses a lock file per server to prevent multiple processes
    from running at the same time. The default is ~/.boartty.servername.lock

Example:

.. code-block: yaml
   servers:
     - name: CHANGEME
       url: https://CHANGEME.example.org/
       token: CHANGEME

Palettes
++++++++

Boartty comes with two palettes defined internally.  The default
palette is suitable for use on a terminal with a dark background.  The
`light` palette is for a terminal with a white or light background.
You may customize the colors in either of those palettes, or define
your own palette.

If any color is not defined in a palette, the value from the default
palette is used.  The values are a list of at least two elements
describing the colors to be used for the foreground and background.
Additional elements may specify (in order) the color to use for
monochrome terminals, the foreground, and background colors to use in
high-color terminals.

For a reference of possible color names, see the `Urwid Manual
<http://urwid.org/manual/displayattributes.html#foreground-and-background-settings>`_

To see the list of possible palette entries, run `boartty --print-palette`.

The following example alters two colors in the default palette, one
color in the light palette, and one color in a custom palette.

.. code-block: yaml
   palettes:
     - name: default
       task-title: ['light green', '']
       task-id: ['dark cyan', '']
     - name: light
       task-project: ['dark blue', '']
     - name: custom
       task-project: ['dark red', '']

Palettes may be selected at runtime with the `-p PALETTE` command
line option, or you may set the default palette in the config file.

**palette**
  This option specifies the default palette.

Keymaps
+++++++

Keymaps work the same way as palettes.  Two keymaps are defined
internally, the `default` keymap and the `vi` keymap.  Individual keys
may be overridden and custom keymaps defined and selected in the
config file or the command line.

Each keymap contains a mapping of command -> key(s).  If a command is
not specified, Boartty will use the keybinding specified in the default
map.  More than one key can be bound to a command.

Run `boartty --print-keymap` for a list of commands that can be bound.

The following example modifies the `default` keymap:

.. code-block: yaml
   keymaps:
     - name: default
       leave-comment: 'r'
     - name: custom
       leave-comment: ['r', 'R']
     - name: osx  # OS X blocks ctrl+o
       story-search: 'ctrl s'


To specify a sequence of keys, they must be a list of keystrokes
within a list of key series.  For example:

.. code-block: yaml
   keymaps:
     - name: vi
       quit: [[':', 'q']]

The default keymap may be selected with the `-k KEYMAP` command line
option, or in the config file.

**keymap**
  Set the default keymap.

Commentlinks
++++++++++++

Commentlinks are regular expressions that are applied to story
descriptions and comments.  They can be replaced with internal or
external links, or have colors applied.

**commentlinks**
  This is a list of commentlink patterns.  Each commentlink pattern is
  a dictionary with the following values:

  **match**
    A regular expression to match against the text of commit or review
    messages.

  **replacements**
    A list of replacement actions to apply to any matches found.
    Several replacement actions are supported, and each accepts
    certain options.  These options may include strings extracted from
    the regular expression match in named groups by enclosing the
    group name in '{}' braces.

  The following replacement actions are supported:

    **text**
      Plain text whose color may be specified.

      **text**
        The replacement text.

      **color**
        The color in which to display the text.  This references a
        palette entry.

    **link**
      A hyperlink with the indicated text that when activated will
      open the user's browser with the supplied URL

      **text**
        The replacement text.

      **url**
        The color in which to display the text.  This references a
        palette entry.

    **search**
      A hyperlink that will perform a Boartty search when activated.

      **text**
        The replacement text.

      **query**
        The search query to use.

This example matches story numbers, and replaces them with a link to
an internal Boartty search for that story.

.. code-block: yaml
   commentlinks:
     - match: "(?P<id>[0-9]+)"
       replacements:
         - search:
             text: "{id}"
             query: "story:{id}"

Story List Options
++++++++++++++++++

**story-list-query**
  This is the query used for the list of storyies when a project is
  selected.  The default is empty.

**story-list-options**
  This section defines default sorting options for the story list.

  **sort-by**
    This key specifies the sort order, which can be `number` (the
    Story number), `updated` (when the story was last updated), or
    `last-seen` (when the story was last opened in Boartty).

  **reverse**
    This is a boolean value which indicates whether the list should be
    in ascending (`true`) or descending (`false`) order.

Example:

.. code-block: yaml
   story-list-options:
     sort-by: 'number'
     reverse: false

Dashboards
++++++++++

This section defines customized dashboards.  You may supply any
Boartty search string and bind them to any key.  They will appear in
the global help text, and pressing the key anywhere in Boartty will
run the query and display the results.

**dashboards**
  A list of dashboards, the format of which is described below.

  **name**
    The name of the dashboard.  This will be displayed in the status
    bar at the top of the screen.

  **query**
    The search query to perform to gather stories to be listed in the
    dashboard.

  **key**
    The key to which the dashboard should be bound.

Example:

.. code-block: yaml

   dashboards:
     - name: "My stories"
       query: "creator:self status:active"
       key: "f2"

General Options
+++++++++++++++

**breadcrumbs**
  Boartty displays a footer at the bottom of the screen by default
  which contains navigation information in the form of "breadcrumbs"
  -- short descriptions of previous screens, with the right-most entry
  indicating the screen that will be displayed if you press the `ESC`
  key.  To disable this feature, set this value to `false`.

**display-times-in-utc**
  Times are displayed in the local timezone by default.  To display
  them in UTC instead, set this value to `true`.

**handle-mouse**
  Boartty handles mouse input by default.  If you don't want it
  interfering with your terminal's mouse handling, set this value to
  `false`.
