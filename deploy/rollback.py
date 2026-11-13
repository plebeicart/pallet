"""Root-run rollback with all backups validated before stopping anything."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


def plan(root: Path, release: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', release):
        raise ValueError('Invalid release identifier')
    backup = root / 'var/backups/pallet'
    previous = (backup / f'previous-{release}.txt').read_text().strip()
    target = None
    if previous != 'none':
        target = Path(previous)
        if root != Path('/'):
            target = root / previous.lstrip('/')
        target = target.resolve(strict=True)
        target.relative_to((root / 'opt/pallet-api/releases').resolve(strict=True))
        if not (target / '.venv/bin/python').is_file():
            raise ValueError('Previous release has no Python environment')
    web = backup / f'web-{release}.tgz'
    with tarfile.open(web) as archive:
        for name in ('index.html', 'js/main.js'):
            if not archive.getmember(name).isfile():
                raise ValueError('Invalid web backup')
    caddy = backup / f'Caddyfile-{release}'
    if not caddy.is_file():
        raise ValueError('Missing Caddy backup')
    unit = backup / f'service-{release}'
    if target and not unit.is_file():
        raise ValueError('Missing previous systemd unit')
    return target, web, caddy, unit


def restore(root, release, run):
    target, web, caddy, unit = plan(root, release)
    # Validate the saved configuration before stopping the current service.
    run(['caddy', 'validate', '--config', str(caddy), '--adapter', 'caddyfile'])
    run(['systemctl', 'stop', 'pallet-api'])
    if target:
        current = root / 'opt/pallet-api/current'
        temporary = current.with_name(f'rollback-{os.getpid()}.next')
        temporary.symlink_to(target)
        temporary.replace(current)
        shutil.copyfile(unit, root / 'etc/systemd/system/pallet-api.service')
    with tarfile.open(web) as archive:
        for name in ('index.html', 'js/main.js'):
            destination = root / 'var/www/pallet' / name
            temporary = destination.with_name(destination.name + '.rollback')
            with archive.extractfile(name) as source, temporary.open('wb') as output:
                shutil.copyfileobj(source, output)
            temporary.chmod(0o644)
            temporary.replace(destination)
    shutil.copyfile(caddy, root / 'etc/caddy/Caddyfile')
    run(['systemctl', 'daemon-reload'])
    if target:
        run(['systemctl', 'start', 'pallet-api'])
    else:
        run(['systemctl', 'disable', 'pallet-api'])
    run(['systemctl', 'reload', 'caddy'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('release')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo; backup directory is root-only')
    # Caller must explicitly turn collection off before rollback.
    env = Path('/etc/pallet-api/pallet-api.env').read_text().splitlines()
    if 'REQUESTS_ENABLED=false' not in env or any(line.strip().startswith('REQUESTS_ENABLED=') and line.strip() != 'REQUESTS_ENABLED=false' for line in env):
        parser.error('Set REQUESTS_ENABLED=false in the environment file first')
    restore(Path('/'), args.release, lambda command: subprocess.run(command, check=True))


if __name__ == '__main__':
    main()
