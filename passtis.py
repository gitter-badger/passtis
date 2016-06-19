# -*- coding: utf-8 -*-

import json
import os
import sys
from argparse import ArgumentParser
from getpass import getpass
from time import sleep

import gnupg
import pyperclip

__version__ = '0.1'


def parse_args():
    """
    Handles command-line arguments parsing.
    """
    parser = ArgumentParser(
        description='Passtis - Command line password manager.',
        version=__version__
    )
    parser.add_argument(
        '-d', '--dir',
        help='store location',
        default=os.path.join(os.path.expanduser('~'), '.passtis-store')
    )
    parser.add_argument(
        '-V', '--verbose',
        help='display GnuPG debug information',
        action='store_true'
    )

    subparsers = parser.add_subparsers(dest='command')

    init_parser = subparsers.add_parser('init', help='initialize the password store')
    init_parser.add_argument('key_id', help='ID of the key used for encrypting the store')

    # TODO: allow to generate a password instead of prompting for one
    add_parser = subparsers.add_parser('add', help='add a new entry')
    add_parser.add_argument('name', help='entry name')
    add_parser.add_argument(
        '-u', '--user',
        help='user name',
        default=''
    )
    add_parser.add_argument(
        '-U', '--uri',
        help='resource URI',
        default=''
    )
    add_parser.add_argument(
        '-c', '--comment',
        help='additional entry information',
        default=''
    )
    add_parser.add_argument(
        '-g', '--group',
        help='group the entry belongs to',
        default='default'
    )

    del_parser = subparsers.add_parser('del', help='delete an entry')
    del_parser.add_argument('name', help='entry name')
    del_parser.add_argument(
        '-g', '--group',
        help='group the entry belongs to',
        default='default'
    )
    del_parser.add_argument(
        '-y', '--yes',
        help='do not ask for confirmation',
        action='store_true'
    )

    list_parser = subparsers.add_parser('list', help='list store entries')
    list_parser.add_argument(
        '-G', '--groups',
        help='display only entries from GROUPS',
        nargs='+'
    )

    get_parser = subparsers.add_parser('get', help='fetch an entry from the store')
    get_parser.add_argument('name', help='entry name')
    get_parser.add_argument(
        '-g', '--group',
        help='group the entry belongs to',
        default='default'
    )
    get_parser.add_argument(
        '-e', '--echo',
        help='display password instead of copying it to the clipboard',
        action='store_true'
    )
    get_parser.add_argument(
        '-s', '--silent',
        help='do not output anything',
        action='store_true'
    )

    return parser.parse_args()


def get_key_id(path):
    """
    Gets key ID for the store located at specified location.
    """
    key_path = os.path.join(path, '.key-id')
    if not os.path.isfile(key_path):
        print('Key ID file not found: {}'.format(key_path))
        sys.exit(66)
    with open(key_path) as ifile:
        data = ifile.read().strip()
    return data


def check_store_dir(path):
    """
    Checks if specified store location exists and has a .key-id file.
    """
    if not os.path.exists(path):
        print('Store directory does not exist')
        sys.exit(66)
    key_path = os.path.join(path, '.key-id')
    if not os.path.exists(key_path):
        print('No key ID found: {}'.format(key_path))
        sys.exit(66)


def daemonize():
    """
    Do UNIX double-fork magic to daemonize current process.
    Shamelessly taken from https://github.com/serverdensity/python-daemon
    """
    try:
        pid = os.fork()
        if pid > 0:
            # exit from first parent
            sys.exit(0)
    except OSError as err:
        print('Fork #1 failed: {} ({})'.format(err.strerror, err.errno))
        sys.exit(1)
    os.setsid()

    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent
            sys.exit(0)
    except OSError as err:
        print('Fork #2 failed: {} ({})'.format(err.strerror, err.errno))
        sys.exit(1)


def store_init(args):
    """
    Initializes Passtis store.
    """
    # TODO: check if key with specified ID exists and is sufficiently trusted
    if os.path.exists(args.dir):
        print('Directory already exists: {}'.format(args.dir))
        sys.exit(73)
    key_path = os.path.join(args.dir, '.key_id')
    os.mkdir(args.dir, 0o700)
    with open(key_path, 'w') as ofile:
        ofile.write(args.key_id)
    print('New store created: {}'.format(args.dir))


def store_add(args):
    """
    Adds a new entry to the store.
    """
    check_store_dir(args.dir)
    key_id = get_key_id(args.dir)
    output_dir = os.path.join(args.dir, args.group)
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir, 0o700)
    output_file = os.path.join(output_dir, args.name)
    if os.path.exists(output_file):
        print('Entry already exists: {}/{}'.format(args.group, args.name))
        sys.exit(73)

    gpg = gnupg.GPG(verbose=args.verbose)
    data = {
        'username': args.user,
        'uri': args.uri,
        'comment': args.comment
    }
    password1 = getpass('Password: ')
    password2 = getpass('Confirm password: ')
    if password1 != password2:
        print("Passwords don't match!")
        sys.exit(1)
    data['password'] = password1
    jsoned = json.dumps(data)
    gpg.encrypt(jsoned, [key_id], armor=True, output=output_file)
    os.chmod(output_file, 0o600)


def store_del(args):
    """
    Deletes an entry from the store.
    """
    check_store_dir(args.dir)
    entry_path = os.path.join(args.dir, args.group, args.name)
    if not os.path.isfile(entry_path):
        print('No such entry: {}/{}'.format(args.group, args.name))
        sys.exit(66)
    os.unlink(entry_path)
    print('Entry removed: {}/{}'.format(args.group, args.name))


def store_list(args):
    """
    Lists stored groups and entries.
    """
    # TODO: pretty tree-like display
    check_store_dir(args.dir)
    print('\n===== {} =====\n'.format(args.dir))
    for folder in os.listdir(args.dir):
        if os.path.isdir(os.path.join(args.dir, folder)):
            if args.groups and folder not in args.groups:
                continue
            print('----- {} -----'.format(folder))
            for entry in os.listdir(os.path.join(args.dir, folder)):
                print('* {}'.format(entry))
            print('')


def store_get(args):
    """
    Reads an entry from the store.
    """
    check_store_dir(args.dir)
    entry_path = os.path.join(args.dir, args.group, args.name)
    if not os.path.isfile(entry_path):
        print('No such entry: {}/{}'.format(args.group, args.name))
        sys.exit(66)

    gpg = gnupg.GPG(verbose=args.verbose)
    with open(entry_path) as ifile:
        raw = gpg.decrypt_file(ifile).data
        data = json.loads(raw)
    if not args.silent:
        print('{0} {1}/{2} {0}'.format('-' * 10, args.group, args.name))
        for key in ('URI', 'Username', 'Comment'):
            if key.lower() != 'password':
                print('{:9}: {}'.format(key, data[key.lower()]))
        if args.echo:
            print('Password: {}'.format(data['password']))
        print('-' * (23 + len(args.group + args.name)))
    pyperclip.copy(data['password'])
    if not args.silent and not args.echo:
        print('password copied to clipboard (will be cleared in 30s)')

    daemonize()
    sleep(30)
    pyperclip.copy('')


def main():
    commands = {
        'init': store_init,
        'add': store_add,
        'del': store_del,
        'list': store_list,
        'get': store_get
    }
    args = parse_args()
    commands[args.command](args)


if __name__ == '__main__':
    main()