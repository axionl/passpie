from tempfile import mkdtemp, NamedTemporaryFile
import re
import os

from .proc import run
from .utils import which, yaml_dump, yaml_load


GPG_HOMEDIR = os.path.expanduser('~/.gnupg')
DEVNULL = open(os.devnull, 'w')
DEFAULT_RECIPIENT = "passpie@localhost"
KEY_INPUT = u"""Key-Type: RSA
Key-Length: {}
Subkey-Type: RSA
Name-Comment: {}
Passphrase: {}
Name-Real: {}
Name-Email: {}
Expire-Date: {}
%commit
"""


def make_key_input(**kwargs):
    kwargs.setdefault("key_length", 4096)
    kwargs.setdefault("name", "Passpie")
    kwargs.setdefault("email", DEFAULT_RECIPIENT)
    kwargs.setdefault("comment", "Generated by Passpie")
    kwargs.setdefault("expire_date", 0)
    key_input = KEY_INPUT.format(
        kwargs["key_length"],
        kwargs["comment"] or "Generated by passpie",
        kwargs["passphrase"],
        kwargs["name"],
        kwargs["email"],
        kwargs["expire_date"],
    )
    return key_input


def list_keys(homedir, emails=False):
    command = [
        "gpg",
        '--no-tty',
        "--batch",
        '--fixed-list-mode',
        '--with-colons',
        "--homedir", homedir,
        "--list-keys",
        "--fingerprint",
    ]
    response = run(command)
    keys = []
    for line in response.std_out.splitlines():
        if emails is True:
            mobj = re.search(r'uid:.*?<(.*?@.*?)>:', line)
        else:
            mobj = re.search(r'fpr:.*?(\w+):', line)
        if mobj:
            found = mobj.group(1)
            keys.append(found)
    return keys


def export_keys(homedir, fingerprint):
    command = [
        which('gpg2', 'gpg'),
        '--no-tty',
        '--batch',
        '--homedir', homedir,
        '--export',
        '--armor',
        fingerprint,
    ]
    command_secret = [
        which('gpg2', 'gpg'),
        '--no-tty',
        '--batch',
        '--homedir', homedir,
        '--export-secret-keys',
        '--armor',
        fingerprint,
    ]
    ret = run(command)
    ret_secret = run(command_secret)
    return ret.std_out + ret_secret.std_out


def create_keys(passphrase, key_length=4096):
    homedir = mkdtemp()
    command = [
        which('gpg2', 'gpg'),
        '--batch',
        '--no-tty',
        '--homedir', homedir,
        '--gen-key',
    ]
    key_input = make_key_input(passphrase=passphrase, key_length=key_length)
    run(command, data=key_input)
    return export_keys(homedir, DEFAULT_RECIPIENT)


def generate_key(homedir, values):
    command = [
        which('gpg2', 'gpg'),
        '--batch',
        '--no-tty',
        '--homedir', homedir,
        '--gen-key',
    ]
    key_input = make_key_input(**values)
    run(command, data=key_input)


def encrypt_data(data, recipient, homedir):
    command = [
        which('gpg2', 'gpg'),
        '--batch',
        '--no-tty',
        '--always-trust',
        '--armor',
        '--recipient', recipient,
        '--homedir', homedir,
        '--encrypt'
    ]
    ret = run(command, data=data)
    return ret.std_out


def decrypt_data(data, recipient, homedir, passphrase):
    command = [
        which('gpg2', 'gpg'),
        '--batch',
        '--no-tty',
        '--always-trust',
        '--recipient', recipient,
        '--homedir', homedir,
        '--passphrase', passphrase,
        '-o', '-',
        '-d', '-',
    ]
    response = run(command, data=data)
    return response.std_out


def import_keys(keyspath, homedir):
    cmd = (
        "gpg",
        "--no-tty",
        "--batch",
        "--homedir", homedir,
        '--allow-secret-key-import',
        "--import", keyspath,
    )
    response = run(cmd)
    return response


def create_homedir(keys):
    homedir = mkdtemp()
    for key in keys:
        keysfile = NamedTemporaryFile(delete=False, dir=homedir, suffix=".asc")
        keysfile.write(key)
        import_keys(keysfile.name, homedir)
    return homedir


class GPG(object):

    def __init__(self, path, passphrase, recipient=None):
        self.path = path
        self.keys = yaml_load(self.path)
        self.homedir = create_homedir(self.keys)
        self.passphrase = passphrase
        self.recipient = recipient or self.get_default_recipient()

    def write(self):
        if len(self.list_keys()) != len(self.keys):
            return yaml_dump(self.export(), self.path)

    def get_default_recipient(self):
        return self.list_keys()[0]

    def list_keys(self, emails=True):
        return list_keys(self.homedir, emails=emails)

    def export(self):
        keys = []
        for fingerprint in self.list_keys():
            keyasc = export_keys(self.homedir, fingerprint)
            keys.append(keyasc)
        return keys

    def encrypt(self, data):
        return encrypt_data(data, self.recipient, self.homedir)

    def decrypt(self, data):
        return decrypt_data(data, self.recipient, self.homedir, self.passphrase)