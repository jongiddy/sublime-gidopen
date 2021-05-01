# Sublime GidOpen

Context menu that runs inside Sublime Text.

## Install

Clone this repo into your Sublime Text packages repository.

For example:
```
cd ~/.config/sublime-text-3/Packages
git clone git@github.com:jongiddy/sublime-gidopen.git
```

To find the `Packages` path use the Sublime Text menu `Preferences / Browse Packages...`

## Update

Update by pulling the latest version.

```
cd ~/.config/sublime-text-3/Packages/sublime-gidopen
git pull
```

## Use

Right-click on a point in the text. If the text around the point looks 
like a filename, then a menu item will be available to open the file.
If line and column information is also available, the menu will go to
the specific location in the file.

If the clicked path is a directory in the project folders, the menu
will reveal the folder.
If outside the project folders, it will add the folder to the project.

If GidOpen does not find the correct filename, select the correct
filename and right-click on the selected text.  In this case, as well
as opening an existing file, the menu will allow creation of the file
if it does not exist.

In text inputs and the console, the context menu only works if the
path is selected.  In these windows, if there is no selection or the
selected text is not a path, the message "GidOpen requires path to
be selected here" will be shown.
