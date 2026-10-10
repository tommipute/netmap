/**
 * Nome corto di una porta per la mappa, come lo scrivono gli apparati nella CLI (Cisco, Arista, Juniper…):
 * TenGigabitEthernet1/1/1 -> Te1/1/1, TwentyFiveGigE1/0/3 -> Twe1/0/3, Port-channel1 -> Po1. I nomi già corti
 * (port1, ge-0/0/1, x1) restano com'erano. Il nome intero si vede passando sopra al nome e nel pannello del cavo.
 */
const SHORT = [
  [/^HundredGig(?:abit)?E(?:thernet)?/i, 'Hu'],
  [/^FortyGig(?:abit)?E(?:thernet)?/i, 'Fo'],
  [/^TwentyFiveGig(?:abit)?E(?:thernet)?/i, 'Twe'],
  [/^TenGig(?:abit)?E(?:thernet)?/i, 'Te'],
  [/^FiveGig(?:abit)?E(?:thernet)?/i, 'Fi'],
  [/^TwoGig(?:abit)?E(?:thernet)?/i, 'Tw'],
  [/^AppGig(?:abit)?E(?:thernet)?/i, 'Ap'],
  [/^Gig(?:abit)?E(?:thernet)?/i, 'Gi'],
  [/^FastE(?:thernet)?/i, 'Fa'],
  [/^Ethernet/i, 'Eth'],
  [/^Port-?channel/i, 'Po'],
  [/^Bundle-Ether/i, 'BE'],
  [/^Management/i, 'Mgmt'],
]

export function shortPortName(name) {
  if (!name) return name
  for (const [pattern, short] of SHORT) {
    const match = pattern.exec(name)
    if (match && /^\s*\d/.test(name.slice(match[0].length))) return short + name.slice(match[0].length).trimStart()
  }
  return name
}
