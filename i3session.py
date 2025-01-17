import os
import i3
import sys
import pickle
import subprocess
import logging
from time import sleep
from xdg.BaseDirectory import *


class Node:
    def __init__(self, data, parent=None):
        self._data = data
        self._parent = parent
        
    @property
    def parent(self):
        """I'm the 'parent' property."""
        return self._parent


    @parent.setter
    def parent(self, value):
        self._parent = value
        
    @property
    def data(self):
        """I'm the 'data' property."""
        return self._data


    @data.setter
    def data(self, value):
        self._data = value

    def __str__(self):
        dictionary = {
            'id': self.data['id'],
            'name': self.data['name'],
            'orientation': self.data['orientation']
        }

        if 'process' in self.data:
            dictionary['process'] = self.data['process']
        if self.parent:
            dictionary['parent'] = self.parent.data['id']

        return str(self.__class__) + str(dictionary)

    @property
    def children(self):
        return self.data['nodes']

    def has_children(self):
        return 'nodes' in self.data

    # xprop WM_CLASS -id ID
    def get_wm_class(self):
        output = subprocess.check_output(["xprop", "WM_CLASS", "-id", str(self.data['window'])])
        return output.split()[3].strip(b'"').lower()

    def restore(self):
        # Use orientation of parent container
        if self.parent and self.parent.data['orientation'] != 'none':
            logging.debug("orientation is now %s", self.parent.data['orientation'])
            i3.command('split', self.parent.data['orientation'])

        # This is a workspace
        if isinstance(self, Workspace):
            # Switch to workspace
            logging.debug("switching to workspace %s", str(self.data['num']))
            i3.command('workspace', str(self.data['num']))
            Tree.sleep_until_changed()
        # This is a client
        elif isinstance(self, Client):
            # Start this process
            logging.debug("exec %s", self.data['process'])
            i3.command('exec', self.data['process'].decode("utf-8"))
            Tree.sleep_until_changed()
            i3.command('focus', 'parent')
            Tree.sleep_until_changed()
        elif isinstance(self, Container):
            pass
class Workspace(Node): pass


class Client(Node): pass


class Container(Node): pass


class Tree():
    CHANGE_TIMEOUT = 0.2
    CHANGE_RETRY = 5

    # for each node that has a window, get WM_CLASS
    @classmethod
    def assign_processes(self, nodes):
        for n in nodes:
            # Recurse subtree
            if n['nodes']:
                n['nodes'] = Tree.assign_processes(n['nodes'])
            # Window ID is set for this client
            elif n['window']:
                # get process from xprop
                node = Node(n)
                n[u'process'] = node.get_wm_class()

        return nodes

    # set up workspaces, exec clients
    @classmethod
    def restore(self, nodes, parent=None, only_workspace=None):
        for n in nodes:
            if 'num' in n:
                node = Workspace(n, parent)
            elif 'process' in n:
                node = Client(n, parent)
            else:
                node = Container(n, parent)

            logging.debug(node)
            node.restore()

            # Recurse subtree
            if node.has_children() == True:
                if only_workspace and isinstance(node, Workspace) and str(node.data['num']) != only_workspace:
                    break
                else:
                    self.restore(node.children, node, only_workspace)

    # TODO: a subscription should be able to pick this up
    @classmethod
    def sleep_until_changed(self):
        i = 0
        original_tree = i3.get_tree()

        while i < Tree.CHANGE_RETRY:
            i += 1
            sleep(Tree.CHANGE_TIMEOUT)
            if original_tree != i3.get_tree():
                break


# use i3-nagbar to show a message while restoring
def nag_bar_process():
    return subprocess.Popen(["i3-nagbar", "-m", "Currently restoring session. Don't change workspace focus!"])


# print usage instructions
def show_help():
    print(sys.argv[0] + " <save|restore> [workspace]")


if __name__ == '__main__':
    # logging.basicConfig(level=logging.DEBUG)

    # If ~/.i3 doesn't exist use XDG_CONFIG_DIR
    home = os.getenv("HOME")
    config_dir = os.path.join(home, '.i3')

    if not os.path.isdir(config_dir):
        config_dir = os.path.join(xdg_config_home, 'i3')

    config_file = os.path.join(config_dir, 'session')

    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)

    if sys.argv[1] == 'save':
        print("Saving...")
        session = i3.get_tree()

        # traverse tree and assign node processes before storing
        if session['nodes']:
            session['nodes'] = Tree.assign_processes(session['nodes'])

        pickle.dump(session, open(config_file, "wb"))
        print("Session saved to " + config_file)
    elif sys.argv[1] == 'restore':
        nag_bar = nag_bar_process()
        print("Restoring...")

        # load session from file
        try:
            session = pickle.load(open(config_file, "rb"))
        except Exception:
            print("Can't restore saved session...")
            sys.exit(1)

        # traverse tree and send commands to i3 based on what was saved
        if 'nodes' in session:
            if len(sys.argv) > 2:
                Tree.restore(session['nodes'], None, sys.argv[2])
            else:
                Tree.restore(session['nodes'])

        nag_bar.terminate()
        print("Session restored from " + config_file)
    else:
        show_help()
        sys.exit(1)
