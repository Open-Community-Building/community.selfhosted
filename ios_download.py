#!/usr/bin/env python3
"""
Download files from an iOS device.
Usage:
    python3 ios_file_download.py
"""
import os
import asyncio
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService
from project_registry import select_projects

projects = select_projects()

async def download_files(project, download_dir):
    lockdown = await create_using_usbmux()
    for projectid in projects.keys():
        project = projects[projectid]
        if project["source"] not in ["IPhone", "IPad"]:
            continue
        info = lockdown.all_values
        if info["UniqueDeviceID"] != project["source_UniqueDeviceID"]:
            continue
        else:
            break

    async with AfcService(lockdown) as afc:
        # Create download directory if it doesn't exist
        os.makedirs(download_dir, exist_ok=True)

        # Walk through the device's file system
        async for root, dirs, files in afc.walk("/"):
            for name in files:
                path = root.rstrip("/") + "/" + name
                # Create corresponding directory structure on local machine
                local_path = os.path.join(download_dir, root.lstrip("/"), name)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                # Download the file
                try:
                    with open(local_path, 'wb') as f:
                        data = await afc.read(path)
                        f.write(data)
                    print(f"Downloaded: {path} to {local_path}")
                except Exception as e:
                    print(f"Error downloading {path}: {str(e)}")

def main():
    for project in projects.values():
        if project["source"] in ["IPhone", "IPad"]:
            download_dir = os.path.join(os.path.dirname(project['dump_pymobiledevice3_files']), "downloaded_files")
            asyncio.run(download_files(project, download_dir))

if __name__ == "__main__":
    main()