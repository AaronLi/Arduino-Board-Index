import os
import chevron
import requests
import json
from typing import Dict, List, Union

def version_ordering(a: List[int], b: List[int]):
    """
    Compares two version numbers represented as lists of integers.

    Args:
        a (list): The first version number.
        b (list): The second version number.

    Returns:
        int: -1 if a < b, 0 if a == b, 1 if a > b.
    """
    for a_sub_version, b_sub_version in zip(a, b):
        if a_sub_version < b_sub_version:
            return -1
        elif a_sub_version > b_sub_version:
            return 1
    return 0

def get_released_boards(per_page=30):
    """
    Retrieves the released versions of the Arduino Boards from the GitHub API.

    Args:
        per_page (int): The number of releases to retrieve per page. Defaults to 30.

    Returns:
        dict: A dictionary containing the released versions of the Arduino Boards, indexed by platform.
    """
    released_versions = {}
    page_number = 0
    manifest_content = {}
    while True:
        releases = requests.get('https://api.github.com/repos/AaronLi/Arduino-Boards/releases', headers={"accept": "application/vnd.github+json", 'per_page':str(per_page), 'page':str(page_number), "X-Github-Api-Version": '2022-11-28'}).json()
        for release in releases:
            for asset in release['assets']:
                if asset['name'] == 'manifest.json':
                    release_manifest_content = requests.get(asset['browser_download_url']).json()
                    for platform in release_manifest_content:
                        platform_version = list(map(int, release_manifest_content[platform]['version'].split('.')))
                        if platform not in manifest_content or version_ordering(manifest_content[platform]['version'], platform_version) < 0:
                            manifest_content[platform] = {'boards': release_manifest_content[platform]['boards'], 'version': platform_version, 'architecture': release_manifest_content[platform]['architecture']}
                    continue
                else:
                    version, hash_platform_file = asset['name'].split('_', 1)
                    hash, platform_file = hash_platform_file.split('_', 1)
                    platform, extension = platform_file.split('.', 1)
                    print(f"Version {version} for {platform} filetype {extension} with sha256 {hash}")
                    released_versions[platform] = {"version": list(map(int, version.split('.'))), "url": asset["browser_download_url"], 'filename': asset['name'], 'filesize': asset['size']}

        if len(releases) < per_page:
            break
        page_number += 1
    return manifest_content, released_versions

def create_tag_name():
    return "latest"

def create_release_title():
    return "New Board Index Released"

def create_release_body():
    return "testing"

def create_release(auth_token: str):
    release_body = {
                "tag_name": create_tag_name(),
                "draft": True,
                "name": create_release_title(),
                "body": create_release_body(),
            }

    response = requests.post(
        'https://api.github.com/repos/AaronLi/Arduino-Board-Index/releases',
          headers={
              "accept": "application/vnd.github+json",
               'Authorization': f'Bearer {auth_token}',
               "X-Github-Api-Version": '2022-11-28'
            },
            data=json.dumps(release_body))
    print(response.json())
    return response.json()['id']

def upload_assets(auth_token: str, release_id: str, index_content: str):
    response = requests.post(
                f'https://uploads.github.com/repos/AaronLi/Arduino-Board-Index/releases/{release_id}/assets?name=package_dumfing_boards_index.json',
                headers={
                    "accept": "application/vnd.github+json",
                    'Authorization': f'Bearer {auth_token}',
                    "X-Github-Api-Version": '2022-11-28',
                    'Content-Type': 'application/octet-stream'
                },
                data=index_content)
    print(response.json()['name'], response.json()['state'])


with open('templates/package_dmfg_index_template.json.mustache', 'r') as f:
    index_template = f.read()

with open('templates/platform_template.json.mustache', 'r') as f:
    platform_template = f.read()


manifest_info, released_boards = get_released_boards()
print(released_boards)
print(manifest_info)
platform_entries = []
for platform in released_boards:
    version, checksum_platform_file = released_boards[platform]['filename'].split('_', 1)
    checksum, platform_file = checksum_platform_file.split('_', 1)
    platform_info = chevron.render(platform_template, 
                   {
                        'platform_name': platform,
                        'architecture': manifest_info[platform]['architecture'],
                        'version': '.'.join(map(str, manifest_info[platform]['version'])),
                        'boards': manifest_info[platform]['boards'],
                        'url': released_boards[platform]['url'],
                        'filename': released_boards[platform]['filename'],
                        'size_bytes': released_boards[platform]['filesize'],
                        'sha256_checksum': checksum,
                   }
    )
    platform_entries.append(platform_info)

dmfg_index = chevron.render(index_template, {'platforms': platform_entries})

release_id = create_release(os.environ['GH_API_TOKEN'])

upload_assets(os.environ['GH_API_TOKEN'], release_id, dmfg_index)