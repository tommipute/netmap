# NetMap manual

NetMap keeps your network documentation: devices with their ports, cables, VLANs, subnets and IP addresses, racks
and maps. Data is entered by hand, imported from Excel, a CSV file or NetBox or found by the SNMP scan, which proposes changes and
waits for your approval. NetMap also checks every minute which devices respond, finds the switch port a PC is
connected to and alerts you when a device stops responding.

This manual is for people who use NetMap. Installing and updating the server is covered in the
[README](../README.md) (in Italian). [Versione italiana](manuale.md).

The interface is available in English: pick it on the sign-in page or in the user menu.

## Contents

1. [First sign-in](#1-first-sign-in)
2. [The interface](#2-the-interface)
3. [Where to start](#3-where-to-start)
4. [Catalog: roles, manufacturers, models](#4-catalog-roles-manufacturers-models)
5. [Places: sites, locations, racks](#5-places-sites-locations-racks)
6. [Devices and ports](#6-devices-and-ports)
7. [Cables](#7-cables)
8. [Addressing: subnets, IPs, VLANs, VRFs](#8-addressing-subnets-ips-vlans-vrfs)
9. [Import and export](#9-import-and-export)
10. [Maps](#10-maps)
11. [Rack view](#11-rack-view)
12. [SNMP scan](#12-snmp-scan)
13. [Where is it connected?](#13-where-is-it-connected)
14. [Live status and alerts](#14-live-status-and-alerts)
15. [What changed and history](#15-what-changed-and-history)
16. [Users and Active Directory](#16-users-and-active-directory)
17. [Backups](#17-backups)
18. [Updates and diagnostics](#18-updates-and-diagnostics)
19. [Common problems](#19-common-problems)
20. [API and scripts](#20-api-and-scripts)

## 1. First sign-in

Open the NetMap address in your browser (for example `https://netmap.company.local`). The first time, the page
asks you to create the **administrator**: user name, first name, last name and password (at least 8 characters). From then on
you sign in with user name and password; a session lasts 12 hours.

On the sign-in page and in the user menu (top right) you can choose:

- **Language**: Italian or English, for the browser you are using.
- **Theme**: light, dark or automatic (follows the operating system).

After 5 wrong passwords in a row for the same user you have to wait a minute, and the wait doubles with every
further mistake (up to 15 minutes). It protects against password guessing: wait and try again.

## 2. The interface

- **Menu on the left**, in sections: Network, Places, Addressing, Catalog, SNMP scan, Activity and (administrators
  only) Administration. On a phone it becomes a bar at the top that scrolls sideways.
- **Search at the top**: finds devices by name, serial number or asset tag, IP addresses, MAC addresses (even
  partial, even in Cisco format `aabb.ccdd.eeff`) and DNS names.
- **Live status dots** next to the search: how many devices respond (green) and how many don't (red). Click them to
  open the list of devices in that state.
- **User menu** on the right: your role, theme, language, change password, API documentation, sign out.
- At the bottom of every page: the installed version and the link to the source code.

**Icon-only buttons** tell you what they do when you hover over them (or long-press on a phone): pencil = edit,
bin = delete, plus = new, and so on.

### Lists

Every menu item opens a list with:

- **search** and **filters** in the top bar; filters are kept in the page address, so you can bookmark the link or
  send it to a colleague;
- **column filters** (funnel button): a row under the headers to filter column by column; "(empty)" finds items
  without that value;
- **sorting** by clicking a column header;
- **columns** to show, hide and reorder (**Table columns** button), remembered by the browser;
- **multiple selection** with the boxes on the left: then delete or edit the selected items in bulk (for example
  move 20 devices to another location or change their role).

Devices, ports, cables and IPs have an icon in the **Source** column telling where they come from: the person =
entered by hand (also with the CSV or Excel import), the waves = found by the SNMP scan, the plug (purple) = imported
from another program, for example NetBox; the name is in the tooltip. With the column filters you see only the ones
of one source. In the device page the same icon is next to the ports that were not entered by hand.

### Forms

Fields with an asterisk are required. Drop-down menus end with **"+ New …"** (for example "+ New site…"): create a
missing site, rack, model or role on the fly without losing what you were typing. Almost every object has
**Custom fields**: free name/value pairs (e.g. "Contract" → "CN-2024-18").

### Printing

Device pages, racks and maps have a **Print** button: the sheet is always light, without buttons, with the date
and the name of who printed it. From the browser print window you can also save a PDF.

## 3. Where to start

The order that saves the most time:

1. **Catalog**: roles (switch, router, firewall, access point…) and, if you like, manufacturers and models.
2. **Places**: the site, then buildings, floors and rooms, then the racks.
3. **SNMP profiles and a scan** of the management network: NetMap finds devices, ports, IPs, VLANs and the cables
   between devices that speak LLDP or CDP. You approve.
4. Complete by hand what the scan can't see: patch panels, devices without SNMP, cables to servers.
5. Create a **map** for the site.

If you already have a list in Excel, start with the [import](#devices-from-csv-or-excel); if your network is
documented in NetBox, bring it into NetMap with the [NetBox import](#from-netbox).

## 4. Catalog: roles, manufacturers, models

- **Roles**: what a device does (Core, Distribution, Access, Firewall, Server…). They have a **colour** (the band on
  the device label in maps) and a **Map level**: 0 at the top, then 1, 2… In the automatic layout firewalls at
  level 0 sit above cores at level 1, which sit above access switches at level 2.
- **Manufacturers** and **Models**: a model has its **height in rack units** (used by the rack view), part number,
  SNMP sysObjectID (how the scan recognises the model) and a **default role**, given automatically to devices of
  that model that have no role.

## 5. Places: sites, locations, racks

- **Sites**: a physical site with its address. Devices, racks, VLANs and subnets belong to a site.
- **Locations**: inside a site, as a tree with as many levels as you want: "Building A" → "Floor 1" → "Server
  room". They are shown with the full path ("Building A › Floor 1 › Server room"). **Floor (height)** orders
  sibling locations from top to bottom: in maps floor 2 is drawn above floor 1.
- **Racks**: name, site, location and height in units (usually 42). A device placed in a rack takes the rack's
  location; moving the rack to another room moves its devices too.

## 6. Devices and ports

A **device** has a name, status (active, planned, offline, decommissioned), site, location, rack and unit, role,
model, serial number, asset tag and **management IP**. The management IP is the address NetMap uses to check it
(ping and SNMP): write it with the mask (`10.0.99.11/24`). NetMap puts it on the device's management port, or
creates one ("mgmt") if there is none.

### Device page

Click a device to open its page:

- **Ports** (management ports first, then in natural order: Gi1/0/2 before Gi1/0/10), with operational status,
  VLANs, IPs, cable and what is on the other side. Each port has a name, type (copper, fibre, wireless, virtual,
  LAG), speed, VLAN mode (access with one untagged VLAN, trunk with tagged VLANs), MAC, MTU, the LAG it belongs to,
  enabled yes/no, management only yes/no.
- **Add ports in bulk**: write a range in square brackets: `Gi1/0/[1-48]` creates 48 ports, `[1-52]` creates ports
  1 to 52, `Te1/1/[1-4]` the four uplinks.
- **Connect** (the icon on the row of a free port): choose the device and port on the other side and the cable
  type.
- **Connected endpoints**: PCs, phones and printers seen behind that port (see
  [Where is it connected?](#13-where-is-it-connected)).
- **Scan data** (in the device details): last time the scan saw it, sysName and SNMP description.
- **Stack**: if the device is a switch stack, the individual switches are listed here (number, model, serial,
  rack unit). A stack is **one device** with one IP and ports Gi1/0/x, Gi2/0/x…; the scan finds the members by
  itself. Daisy-chained switches with their own IPs stay separate devices.
- **History**: every change to the device, its ports and cables, including the scan's.

When deleting a device you can choose to delete its IPs as well; ports and cables go with it.

## 7. Cables

A cable joins two ports (side A and side B) and has a type (Cat5e, Cat6, Cat6a, multimode or single-mode fibre,
DAC), status (connected, planned, decommissioning), label, colour and length. Create it from the device page
(**Connect**), from the map (dragging from one device to another) or from the **Cables** list. A port has only one
cable. In maps colours follow real conventions: copper blue, multimode fibre aqua, single-mode yellow, DAC dark
grey; planned cables are dashed.

## 8. Addressing: subnets, IPs, VLANs, VRFs

- **Subnets**: `10.0.10.0/24` with status, site, VLAN and VRF. The subnet page shows **usage** (how many addresses
  are used), the registered IPs and the **first free IPs**: click one to assign it.
- **IP addresses**: always with the mask (`10.0.10.25/24`), with status (active, reserved, DHCP, deprecated), the
  device port it belongs to, DNS name, VRF. A device has only one management IP.
- **VLANs**: ID and name, per site (or global without a site). Ports use them untagged (access) or tagged (trunk).
  The scan reads them from the switches.
- **VRFs**: for networks with separate routing tables; the same IPs and subnets in different VRFs don't clash.

## 9. Import and export

### Devices from CSV or Excel

In the **Devices** list:

- **Export to CSV** (opens in Excel) or **to JSON**: exports the devices with the active filters.
- **Import**: upload a CSV or Excel (`.xlsx`) file or paste the text. **Download CSV template** gives you a sample
  file with the right columns; headers can be in English or Italian, and the headers of the NetBox device export
  work too (Name, Site, Rack, Position, Type, Primary IPv4…). Missing sites, locations (also as a path
  "Building A > Floor 1"), racks, manufacturers, models and roles are created.
- From an **Excel** file NetMap reads the first sheet that has the name column (Name, Hostname, Nome…): empty rows
  above the headers are fine, dates become `2026-01-31`. The content goes into the text box, where you check it
  before importing. An old `.xls` file must be saved from Excel as `.xlsx` or CSV.
- **Simulation**: shows what would happen without writing anything. Wrong rows are listed with the reason; the
  others are imported. With **Update devices that already exist** a device with the same name on the same site is
  updated (only with the filled-in cells), not duplicated.

### From NetBox

Administrators only: **Administration → NetBox import**. It copies what is in NetBox (version 3.3 or later) into
NetMap: sites, locations, racks, manufacturers, roles, models, VRFs, VLANs, subnets, devices with ports and stacks,
cables and IP addresses.

1. Enter the NetBox address (the one you open in the browser) and an **API token**: a read-only one is enough (in
   NetBox you create it from your profile, API Tokens). NetMap does not keep it: the worker deletes it when the
   import ends.
2. **Test the connection**: NetMap shows the NetBox version, how many objects there are and the list of sites.
3. Choose **All sites** or **Only the chosen sites**. Objects without a site (VRFs, global VLANs and subnets) always
   come along; with chosen sites you get the IPs of their ports and the free ones inside their subnets.
4. **Simulate the import**: it does all the work and rolls it back at the end, so you see how many objects would be
   created and what problems there are without changing anything. If the numbers look right, **Import**.

The worker runs the import in the background: the page shows the log as it goes and at the end a table with the
objects created, those that were already there and those that did not go through, with the reason. You can close
the page: the latest imports stay in **Previous imports**.

- **It only creates what is missing**. An object already in NetMap (site with the same name, device with the same
  name on the same site, VLAN with the same number on the site, IP with the same address…) stays as it is, even if
  it differs in NetBox. You can run the import again whenever you like: it does not create duplicates.
- Ports are only added to devices created by the import; ports of a device that was already there stay as they are,
  and cables to ports that NetMap doesn't have are skipped.
- A NetBox **stack** (virtual chassis) becomes a single device, with the stack's name and its members, as in the
  SNMP scan.
- A cable that goes through a **patch panel** becomes a direct cable between the two ports, with the patch panel in
  the notes. Cables to circuits, power outlets and consoles are not imported: the log says how many.
- Status, serial number, asset tag, custom fields, port mode (access or trunk) with the VLANs, MAC, speed, LAG,
  cable color and length and the management IP (the NetBox primary IP) come along too. An object that fails
  NetMap's checks is listed among the problems; the others go ahead.
- In the **Change history** the import shows up with the origin "NetBox import" and the name of whoever started it;
  a simulation leaves no trace.

## 10. Maps

A map shows devices and the cables between them. Create one in **Maps** by choosing a site and optionally a location
(only that building or floor):

- **Always show all devices** on: the map automatically contains every device of the site or location, including
  those added later.
- Off: you choose which devices to show (**Add device…**), handy for a map of just the core or the server room.

### Layout

The first time, devices are arranged automatically: roles with the lowest level (firewall, core) at the top, the
others below; devices in the same rack are grouped in a **rack bubble**. With **Locations** on, buildings, floors
and rooms become coloured boxes nested in each other.

Drag devices where you want them and press **Save layout**. **Arrange automatically** recalculates everything.
Clicking the name of a rack or location selects all its devices, to move them together.

### Cables on the map

- To **create a cable**, hover over a device: four dots appear. Drag from one of them to another device and choose
  the ports.
- Cables run at right angles and never pass under a device. **Port names** writes the port name where the cable
  enters the device.
- To **adjust a cable by hand**, click it: the small bars on its segments can be dragged sideways, the dots at the
  ends slide along the device border. Then **Save layout**. **Back to the automatic route** undoes it.
- Click a cable to see its details (ports, type, VLANs) and delete it; click a device to see its details and open
  its page.

### More

- **Search the map**: name or IP of a device, or the MAC or IP of a PC: NetMap selects the switch port it is
  connected to.
- **Highlight a VLAN**: emphasises the cables and devices carrying that VLAN.
- **Live status**: the dot on a device is green if it responds, red if not; the map refreshes every 30 seconds.
- **Export…**: PNG image, SVG drawing, or print / PDF.

## 11. Rack view

The rack page shows the front with the occupied units. With the plus button or by clicking a free unit you add a
device of the site to that unit (NetMap checks it fits, using the model height; if the site has more than 1000
devices a search field appears above the menu). Devices can be **dragged** to another unit
(green = fits, red = occupied) or to **In the rack without a unit**; the X removes them from the rack. Stacks show
each member in its own unit.

## 12. SNMP scan

The scan reads devices over SNMP (v1, v2c or v3): name, model, serial number, ports, IPs, VLANs, stack members and
LLDP/CDP neighbours (that is, the cables between devices). **It never changes data entered by hand on its own**:
it proposes changes that you approve.

### Preparation

1. **SNMP profiles**: the credentials. For v1 and v2c the community, for v3 user, authentication protocol and
   key, privacy protocol and key. Use v1 only for old devices that don't know v2c: it is slower and does not read
   64-bit counters. They are stored encrypted and cannot be read back: when editing, leave the field empty
   to keep them.
2. On the devices: SNMP enabled read-only, and the NetMap server address allowed in the ACLs. UDP port 161 must be
   open from the NetMap server to the devices.

### Scans

In **Scans** create a scan with:

- the **addresses**: a network `10.0.99.0/24`, a range `10.0.99.1-10.0.99.40` or `10.0.99.1-40`, a single IP.
  After each one Enter, comma or space turns it into a chip (the × removes it); you can also paste a list. Red chips
  are not valid; below them is the address count (4096 at most);
- the **profiles** to try, in order (the first that answers wins);
- the **Site of the new devices**;
- **Repeat every (hours)**: empty = only when you start it;
- two switches to add **new ports** and **new IPs** of devices already in NetMap without asking.

Open the scan and press **Start scan**: in a few seconds (a few minutes for large networks) you get the result and
the log in the run history.

### To approve

**To approve** (with the counter next to it) collects what the scan found, grouped by device: new devices with
ports and IPs, new ports and IPs, changed data, cables seen via LLDP/CDP, VLANs, stack members, ports that
disappeared. Approve or reject one change, all changes of a device, or all of them.

- Always to approve: new devices, cables, disappeared ports, changes to data you entered.
- Without asking: port status, the last time a device was seen and the data of objects created by the scan itself.
- A rejected change is not proposed again as long as the data stays the same.
- The scan never renames a device.

The trick for cables: approve the new devices first, then run the scan again. Cables are seen only when both
devices are already in NetMap.

## 13. Where is it connected?

After every scan NetMap combines the switches' MAC tables with the ARP tables of routers and cores. In **Where is it
connected?** search a PC by MAC, IP or DNS name and get switch, port, VLAN, site and room. Uplink ports (those with
a cable to another switch) are discarded, so the result is the real access port. If a PC moves, NetMap remembers
the previous port and when it moved.

## 14. Live status and alerts

Every minute NetMap checks the **active devices with a management IP**: a device responds if it answers ping or
SNMP. The status shows in the dots at the top, in the device list (**Live status** column and filter), on the device
page and in maps. On the device page, **Check now** runs the check immediately.

**Alerts** (Administration → Alerts) sends a message when a device has not responded for a number of minutes and,
if you want, when it responds again. Channels:

- **Email**: SMTP server (STARTTLS 587, SSL 465 or no security on 25), user, password, sender, recipients;
- **Webhook**: Teams (with Workflows, "adaptive card" format), Slack, Mattermost, Google Chat (text format);
- **Telegram**: bot token and chat.

The **delay** avoids an alert for a single lost ping; the **message language** is set per channel. **Test** sends a
test message. If sending fails, the error stays visible in the list and NetMap retries on the next round.

## 15. What changed and history

- **What changed**: a summary of the period you choose (last 24 hours, 7 days or 30 days): changes by origin,
  devices created and deleted, devices not responding and back up, new devices on the network or devices that
  moved port, scans (and failed ones), changes to approve. Each box links to the details.
- **Change history**: every creation, change and deletion, with who did it (a user, the scan, an import, Active
  Directory), when and what changed, field by field. Filter by object type, origin, date and text. Passwords never
  appear: only "changed".

## 16. Users and Active Directory

**Users** (Administration → Users) have a role:

| Role | What they can do |
|---|---|
| Read only | see everything, change nothing |
| Edit | change data and approve scan changes |
| Administrator | everything, including users, alerts, Active Directory, updates and backups |

Disabling a user ends their sessions immediately, as does changing their password. Everyone can change their own
password from the user menu.

### Active Directory

With Active Directory users sign in with their Windows name and password (`mario.rossi`, `COMPANY\mario.rossi` or
`mario.rossi@company.local`) and the role comes from their groups. In **Administration → Active Directory**:

1. **Domain** (`company.local`) and **Domain controllers**, with the full name in their certificate
   (`dc1.company.local`); several domain controllers separated by commas, the first that answers is used.
2. **Security**: LDAPS (port 636) or StartTLS (port 389). The domain controller needs a certificate (usually from
   Active Directory Certificate Services). To verify it, paste or upload the **Domain CA certificate** (exported
   from Windows in Base64 format).
3. **Search base** (optional): limits access to the users of one OU.
4. **Roles from groups**: the administrators' group, the editors' group and the readers' group. Nested groups count
   too; a user in several groups gets the highest role. Users in none of the groups can't sign in, unless you choose
   a role for all other domain users.
5. **Test** with a real user: see whether the connection works, which role they would get and which groups were
   found. Then save and enable.

No service account is needed: NetMap connects with the credentials of the person signing in. The NetMap user is
created at the first sign-in and at every sign-in takes from the domain the role, first name and last name (the First
name and Last name of the Active Directory user, or the display name); that is why password, role, first and last
name of a domain user can't be changed in NetMap (it can be disabled). A user removed from all groups is
rejected at the next attempt and their sessions are closed.

**Always keep a local administrator**: local users sign in with their own password even when the domain does not
answer. If a local user and a domain user have the same name, the local one wins.

## 17. Backups

In **Administration → Backups**:

- **Back up every night** at the time you choose, kept for the days you choose (14 by default). If the server was
  off at that time, the backup runs as soon as it is back on.
- **Back up now**: a backup right away, for example before a large import.
- There is always a backup before every update (how many to keep is set on the Updates page).
- **Download** a backup to your PC; **Upload a backup** from your PC (even one made on another server).
- **Restore this backup**: brings the database back to that moment. NetMap first makes a safety backup of the
  current state; if it doesn't start after the restore, it goes back to the previous state by itself. NetMap does
  not respond for a few minutes. A backup made by a newer version than the installed one is refused: update first.

### Off-server copies

A backup that lives only on the server is lost with the server. In **Off-server copies** add a **destination**:

- **Network folder (SMB)**: a NAS or a Windows share: server, share, folder, user (also `DOMAIN\user`) and password;
- **SFTP**: server, port, folder, user and password or private key. The first time NetMap remembers the server key;
  if it changes (server reinstalled) copying stops until you accept the new one.

**Test the connection** before saving. Every new backup is copied within a minute; copies older than the chosen
days are deleted from the destination. **Backups on the destination** shows what is on the other side and **Bring
back to the server** fetches a backup from there.

### Secrets key

SMTP passwords, SNMP communities, destination passwords and the like are encrypted in the database with a key that
lives on the server, **not in the backup**. Download it (**Download the key**) and keep it safe, or enable **Also
copy the secrets key** on a destination.

**New server after a failure**: install NetMap, upload the backup (or add the destination and bring it back from
there), restore it and sign in with the same users as before. The Secrets key section tells you how many passwords
can't be read: paste the old server's key (**Use the old server key**) and they become readable again.

## 18. Updates and diagnostics

NetMap is updated by a script running on the server, outside the app. In **Administration → Updates** you see the
installed and available versions, the last check and the history:

- **Check now** and **Update now**. An update backs up the database, installs the new version and waits for it to
  start; if it doesn't, it goes back to the previous version (and the previous database) by itself.
- **Automatic updates**: installs new versions as soon as it finds them.
- **Channel**: stable (recommended: final versions only, 1.0.0, 1.0.1, 1.1.0…), beta (test versions too, e.g.
  1.1.0-rc.1) or, only when NetMap is installed from source with git, development (every change as soon as it is on
  GitHub, even untested: for a test server). It never goes back to an older version.
- **Log**: what the script did during the last update.

### Diagnostics

To report a problem: **Collect container logs** (the script collects them within a minute), then **Download
diagnostic package**. It is a zip file with version, configuration without passwords or keys, database status and
logs. The logs may contain IP addresses, device names and user names from your network: have a look before sending
it to anyone.

## 19. Common problems

**The browser says the certificate is not valid.** The standard installation uses an internal CA. Install the CA
certificate on the PCs (instructions in the README, "Certificato" section), or use your own certificate.

**I lost the administrator password.** On the server, in the NetMap folder:
`docker compose exec -it api python -m app.users password admin` (replace `admin` with your user name).

**The scan finds nothing.** The run log says how many hosts answered. A device that doesn't answer usually has a
community or v3 credentials different from the profile, an SNMP ACL that doesn't allow the NetMap server, or UDP
port 161 blocked by a firewall. Try from a PC with an SNMP client using the same data.

**The scan doesn't find cables.** LLDP or CDP must be enabled on both devices, and both must already be in NetMap:
approve the new devices and run the scan again.

**A device is red but works.** The check uses the management IP: make sure it is correct and that the NetMap server
can ping it or reach it over SNMP. A device without a management IP is not checked.

**Where is it connected? doesn't find a PC.** The PC must have communicated recently (switch MAC tables forget a
silent device after a few minutes) and the scan must have read both the access switch and the router or core holding
the ARP table.

**Active Directory: "no domain controller responds".** The NetMap server must resolve the domain controller name
and reach port 636 (or 389). "Certificate issued to another name": write the domain controller with the full name in
its certificate. "Not signed by a known CA": paste the domain CA certificate.

**The Updates page says the script is silent.** On the server: `systemctl status netmap-updater.timer` and
`journalctl -u netmap-updater`.

## 20. API and scripts

Everything the interface does goes through a REST API, documented under **API documentation** in the user menu
(`/docs`). To use it from a script, sign in with `POST /api/auth/login` and send the token you receive in the
`Authorization: Bearer <token>` header; permissions follow the user's role. Lists accept `limit`, `offset`, `q`,
filters and `sort` (e.g. `GET /api/devices?site_id=1&sort=-name`).
