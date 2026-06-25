import asyncio
import json
from pymobiledevice3.lockdown import create_using_usbmux


async def main():
    lockdown = await create_using_usbmux()

    # full root-domain identity dict, populated during the handshake
    info = lockdown.all_values

    groups = {}
    groups["model"] = [
        "DeviceName", "DeviceClass", "ProductName", "ProductType",
        "ModelNumber", "RegionInfo", "HardwareModel",
        "DeviceColor", "DeviceEnclosureColor", "CPUArchitecture",
    ]
    groups["firmware"] = [
        "ProductVersion", "BuildVersion", "FirmwareVersion",
        "BasebandVersion", "BasebandSerialNumber",
    ]
    groups["identifiers"] = [
        "UniqueDeviceID", "SerialNumber", "UniqueChipID", "ChipID",
        "WiFiAddress", "BluetoothAddress", "EthernetAddress",
    ]
    groups["cellular"] = [
        "InternationalMobileEquipmentIdentity",
        "InternationalMobileEquipmentIdentity2",
        "MobileEquipmentIdentifier",
        "IntegratedCircuitCardIdentity", "PhoneNumber",
    ]
    groups["state"] = [
        "ActivationState", "PasswordProtected", "TimeZone",
    ]

    for group_name, keys in groups.items():
        print("[" + group_name + "]")
        for key in keys:
            if key in info:
                print("   ", key, "=", info[key])

    # convenience properties read from the same dict
    print("udid:", lockdown.udid)
    print("type:", lockdown.product_type, "ios:", lockdown.product_version)

    # these are NOT in all_values — separate domains, query explicitly
    battery = await lockdown.get_value(domain="com.apple.mobile.battery")
    disk = await lockdown.get_value(domain="com.apple.disk_usage")
    # Drop opaque binary blobs (e.g. NANDInfo — a multi-KB raw NAND-geometry dump).
    # They aren't human-readable, flood the terminal, and aren't JSON-serializable.
    disk = {k: v for k, v in disk.items() if not isinstance(v, bytes)}
    print("battery:", battery)
    print("disk:", disk)

    # or just dump everything:
    # print(json.dumps(info, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
