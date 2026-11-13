import io
from pathlib import Path
import tarfile
import pytest
from deploy.rollback import restore


@pytest.fixture
def root(tmp_path):
    for folder in ['var/backups/pallet','var/www/pallet/js','etc/caddy','etc/systemd/system','opt/pallet-api/releases/old/.venv/bin']:
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    backup = tmp_path / 'var/backups/pallet'
    backup.chmod(0o700)
    (backup / 'previous-test.txt').write_text('/opt/pallet-api/releases/old')
    (backup / 'service-test').write_text('old unit')
    (backup / 'Caddyfile-test').write_text('old caddy')
    (tmp_path / 'opt/pallet-api/releases/old/.venv/bin/python').write_text('test interpreter')
    (tmp_path / 'opt/pallet-api/current').symlink_to(tmp_path / 'opt/pallet-api/releases/new')
    with tarfile.open(backup / 'web-test.tgz', 'w:gz') as archive:
        for name in ['index.html','js/main.js']:
            content = ('old ' + name).encode()
            member = tarfile.TarInfo(name); member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return tmp_path


def test_restores_previous_release_and_files(root):
    commands=[]
    restore(root, 'test', commands.append)
    assert (root / 'opt/pallet-api/current').resolve() == root / 'opt/pallet-api/releases/old'
    assert (root / 'var/www/pallet/js/main.js').read_text() == 'old js/main.js'
    assert (root / 'etc/systemd/system/pallet-api.service').read_text() == 'old unit'
    assert (root / 'etc/caddy/Caddyfile').read_text() == 'old caddy'
    assert commands[0][:2] == ['caddy','validate']
    assert ['systemctl','start','pallet-api'] in commands


def test_missing_manifest_fails_before_stopping(root):
    (root / 'var/backups/pallet/previous-test.txt').unlink()
    commands=[]
    with pytest.raises(FileNotFoundError): restore(root, 'test', commands.append)
    assert commands == []


def test_first_install_explicit_none(root):
    (root / 'var/backups/pallet/previous-test.txt').write_text('none')
    commands=[]
    restore(root, 'test', commands.append)
    assert ['systemctl','disable','pallet-api'] in commands
    assert ['systemctl','start','pallet-api'] not in commands


def test_failed_caddy_validation_leaves_current_release(root):
    old = (root / 'opt/pallet-api/current').readlink()
    def fail(command): raise RuntimeError('invalid config')
    with pytest.raises(RuntimeError): restore(root, 'test', fail)
    assert (root / 'opt/pallet-api/current').readlink() == old
