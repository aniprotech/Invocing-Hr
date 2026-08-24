# Meetings: what to connect, and why

The meeting room is WebRTC in a mesh: everyone connects directly to everyone
else. There is no media server, which is why it costs nothing to run — and
which is also where both of its limits come from.

## 1. A relay (TURN) — the one that stops people joining at all

**Set this.** Without it a meaningful fraction of users cannot join, and the
way they fail is the worst kind: the call appears to connect, the other
person's tile appears, and no audio or video ever arrives. It looks like a bug
in the app rather than a network that needs a relay.

Two machines can only talk directly if their networks let them. STUN (which is
configured, and free) discovers a direct path where one exists. Where one does
not — symmetric NAT, most corporate firewalls, some mobile carriers — the only
way through is to relay the media via a server that both ends *can* reach.
That is TURN. Published figures put the share of connections needing it
somewhere between 8% and 20%.

Our users are office staff. That is precisely the population behind
restrictive firewalls.

```
TURN_URLS=turn:your-host:3478,turns:your-host:5349
TURN_USERNAME=...
TURN_PASSWORD=...
```

Served to the browser by `/api/meet/ice`, never written into `meeting.html`, so
the credentials are not sitting in a static file and rotating them is an
environment change rather than a deploy. With nothing set the app still serves
STUN and still works for everyone whose network allows a direct path — it just
cannot rescue those it does not, and it says so in the logs at startup and in
the toast a failing user sees.

Include the `turns:` (TLS, port 5349 or 443) URL as well as the plain one.
Firewalls that only allow outbound 443 are common, and it is the TLS URL that
gets through them.

### Options

| | Cost | Notes |
|---|---|---|
| **coturn**, self-hosted | A small VPS | The standard server. Needs a public IP and an open UDP range. Most control, cheapest at volume. |
| **Open Relay** (metered.ca) | Free tier | Fastest way to prove the fix works. Check current limits before relying on it. |
| Twilio / Xirsys / Cloudflare | Per GB | Managed. Sensible if you would rather not run a server. |

Relayed media costs bandwidth on whoever hosts the relay, because it passes
through them. Only the connections that need it use it — the rest still go
direct — so this is usually a small share of traffic.

## 2. Room size — the one that limits how many can be in a call

In a mesh, each person uploads one copy of their video *per other
participant*. Five people means four uploads each. The cost climbs with the
square of the room, and past roughly six the weakest uplink in the call starts
costing everyone frames. The app warns once when a room goes over six.

Removing this ceiling means a server that receives one stream from each person
and forwards it — an SFU. That is real infrastructure, not a setting:

- **LiveKit** — open source, self-hostable, also sold as a managed service.
- **mediasoup** — a library; more control, more to build.
- **Janus** — mature, general purpose.

This is the honest gap between what is here and something like Amazon Chime or
Zoom. Everything else in the room — screen share, chat, recording, captions,
the lobby, raise-hand, device selection — already works. It is the topology
that decides whether ten people can be in a call, and changing it is a project
rather than an afternoon.

## What runs today without connecting anything

Meetings work now, for small groups, on networks that allow a direct path.
Setting TURN is what makes the first part of that sentence true for everybody;
an SFU is what removes the second.
