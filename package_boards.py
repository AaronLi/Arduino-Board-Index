import asyncio
import os
import aiofiles.os
import aiofiles
import chevron
import aiohttp
import json
from datetime import datetime
from collections import defaultdict
from typing import List

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

async def get_released_boards(session: aiohttp.ClientSession, per_page=30):
    """
    Retrieves the released versions of the Arduino Boards from the GitHub API.

    Args:
        per_page (int): The number of releases to retrieve per page. Defaults to 30.

    Returns:
        dict: A dictionary containing the released versions of the Arduino Boards, indexed by platform.
    """
    released_versions = defaultdict(dict)
    page_number = 0
    manifest_content = defaultdict(dict)
    while True:
        async with session.get('https://api.github.com/repos/AaronLi/Arduino-Boards/releases', headers={"accept": "application/vnd.github+json", 'per_page':str(per_page), 'page':str(page_number), "X-Github-Api-Version": '2022-11-28'}) as req:
            releases = await req.json()
            for release in releases:
                for asset in release['assets']:
                    if asset['name'] == 'manifest.json':
                        async with session.get(asset['browser_download_url']) as manifest_req:
                            release_manifest_content = json.loads(await manifest_req.text())
                            for platform in release_manifest_content:
                                version = release_manifest_content[platform]['version']
                                platform_version = list(map(int, version.split('.')))
                                manifest_content[platform][version] = {'boards': release_manifest_content[platform]['boards'], 'version': platform_version, 'architecture': release_manifest_content[platform]['architecture']}
                    else:
                        version, hash_platform_file = asset['name'].split('_', 1)
                        hash, platform_file = hash_platform_file.split('_', 1)
                        platform, extension = platform_file.split('.', 1)
                        print(f"Version {version} for {platform} filetype {extension} with sha256 {hash}")
                        released_versions[platform][version] = {"version": list(map(int, version.split('.'))), "url": asset["browser_download_url"], 'filename': asset['name'], 'filesize': asset['size']}

            if len(releases) < per_page:
                break
            page_number += 1
    return manifest_content, released_versions

def create_tag_name():
    return datetime.utcnow().strftime("v%Y-%m-%dT%H%M")

def create_release_title():
    return "New Board Index Released"

def create_release_body():
    return ""

async def create_release(session: aiohttp.ClientSession, auth_token: str):
    release_body = {
                "tag_name": create_tag_name(),
                "draft": True,
                "name": create_release_title(),
                "body": create_release_body(),
            }
    async with session.post(
        'https://api.github.com/repos/AaronLi/Arduino-Board-Index/releases',
          headers={
              "accept": "application/vnd.github+json",
               'Authorization': f'Bearer {auth_token}',
               "X-Github-Api-Version": '2022-11-28'
            },
            data=json.dumps(release_body)) as req:
        response = await req.json()
        return response['id']

async def upload_assets(session: aiohttp.ClientSession, auth_token: str, release_id: str, index_content: str):
    async with session.post(
                f'https://uploads.github.com/repos/AaronLi/Arduino-Board-Index/releases/{release_id}/assets?name=package_dumfing_boards_index.json',
                headers={
                    "accept": "application/vnd.github+json",
                    'Authorization': f'Bearer {auth_token}',
                    "X-Github-Api-Version": '2022-11-28',
                    'Content-Type': 'application/octet-stream'
                },
                data=index_content) as req:
        response_json = await req.json()
        print(response_json['name'], response_json['state'])

async def main():
    async with aiohttp.ClientSession() as session:
        async with aiofiles.open(os.path.join('templates', 'package_dmfg_index_template.json.mustache')) as index_f:
            async with aiofiles.open(os.path.join('templates', 'platform_template.json.mustache')) as platform_f:
                index_template, platform_template, board_info = await asyncio.gather(index_f.read(), platform_f.read(), get_released_boards(session))
                manifest_info, released_boards = board_info
                print(released_boards)
                print(manifest_info)
                platform_entries = []
                for platform in released_boards:
                    for version in released_boards[platform]:
                        _, checksum_platform_file = released_boards[platform][version]['filename'].split('_', 1)
                        checksum, _ = checksum_platform_file.split('_', 1)
                        platform_info = chevron.render(platform_template, 
                                    {
                                            'platform_name': platform,
                                            'architecture': manifest_info[platform][version]['architecture'],
                                            'version': version,
                                            'boards': manifest_info[platform][version]['boards'],
                                            'url': released_boards[platform][version]['url'],
                                            'filename': released_boards[platform][version]['filename'],
                                            'size_bytes': released_boards[platform][version]['filesize'],
                                            'sha256_checksum': checksum,
                                    }
                        )
                        platform_entries.append(platform_info)

                dmfg_index = chevron.render(index_template, {'platforms': map(lambda x: {'entry': x[1]} if x[0]+1 < len(platform_entries) else {'entry': x[1], 'last': True}, enumerate(platform_entries))})
                sanity_check = json.loads(dmfg_index)
                release_id = await create_release(session, os.environ['GH_API_TOKEN'])

                await upload_assets(session, os.environ['GH_API_TOKEN'], release_id, dmfg_index)

if __name__ == '__main__':
    asyncio.run(main())