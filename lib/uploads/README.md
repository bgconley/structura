# Durable upload attempt backend

Implementation candidate for migration 104, pending the root-owned isolated Linux
PostgreSQL/API gate. This package does not activate native processing or change
ordinary Viewer/search publication. The legacy intake API retains its own contract;
its writers share only the household/hash admission lock and intake repositories.

`UploadCreate` pins the actor/household operation UUID and exact immutable metadata.
Every PUT takes `If-Match: <revision UUID>` before body consumption. Replacing an
unfinished transfer additionally requires `X-Replace-Transfer-ID: <exact current ID>`.
A replacement uses a new generation and file; it does not free the previous lease's
bytes. Accepted PUT replays are admitted, streamed and hashed again; different bytes
conflict. GET is the preferred lost-response reconciliation. `recordedAt` is this
operation's receipt time; reuse does not invent a new ingest job or historical
original acceptance timestamp. New acceptance uses the existing intake repositories
for the original/document/jobs and commits the receipt in that same transaction.

All mutation admission takes the global upload-capacity advisory lock, then the
household/hash admission namespace when known, then the captured RequestCredential
prefix, operation/transfer, document/folder/ACL/source, content hash and job locks.
A final fresh database-clock check verifies the exact originating credential,
metadata, generation, internal token and source binding. Short SQL statements have
5 second statement and 3 second lock limits; connections have a 5 second connect bound.
Neither raw body IO nor full-file hashing occurs under SQL locks. Durable processing
jobs retain ADR0010/097's separate lifetime after original acceptance.

The canonical filesystem contains a private `.upload-attempts` directory. UUID lock
files permanently retain their inode; cleanup never unlinks them. A writer opens a
new UUID data file once with O_EXCL and O_NOFOLLOW, holds its stable flock through
closed-file verification, publication and cleanup, and never reopens a verified
generation for writing. Non-abandoning bounded write calls retain ownership until
actual IO stops. Decision commands lock the original held source transfer, not just
their new zero-byte decision lease. OS locks are acquired outside SQL, nonblocking
with a bounded retry window. Expiry/cancel revokes authority immediately but cannot
release capacity while a writer still holds that lock.

Publication prepares a temporary hardlink on the same filesystem. Data and its
publication link share one inode; no second full-file copy escapes the reservation.
An existing canonical file is hashed using an open FD outside SQL, with before/after
FD and non-following path comparisons. Under the content lock, reuse requires the
same regular-file device/inode/size/mtime_ns/ctime_ns. A changed preparation retries
outside SQL. A missing destination is installed atomically from the closed verified
inode. Its actual created flag is preserved through rollback. These guarantees cover
participating Structura storage writers and cleanup, not arbitrary external mutation
of managed directories. A filesystem without these primitives fails closed.

`clean_expired_uploads(staging, policy, limit=100)` is the bounded maintenance entry
point; scheduling it remains an operational integration prerequisite. Cleanup first
commits an opaque cleanup claim, then obtains the stable source lock, checks any
transfer-owned canonical link under the content lock and shared reference query,
removes the data/publication links, fsyncs the directory, and only then confirms quota
release. A referenced same-inode original stays. Another inode is never inferred to
be owned from its hash. A changed identity after lock waits fails without releasing
the reservation. Eligible awaiting_content operations expire after a configurable 30 minutes; registration
also expires that actor's old slots before checking capacity. Active/held or
unconfirmed running IO cannot expire through this inactivity rule.
Permanent operation and transfer tombstones prevent old keys from
creating another original. A crashed decision's own lease can be collected without
expiring a still-valid held source. Maintenance must run before calling crash/held
expiry cleanup operationally complete; no background scheduler is installed here.

Validation defaults are configurable `STRUCTURA_UPLOAD_*` settings:2 actor/4 global
active transfers,200/400 MiB reserved storage,100 pending references,100 MiB per file,
10 minute absolute transfer/30 second idle deadline,30 minute held duplicate retention and inactive-operation expiry.
They are validation limits, not measured throughput or latency guarantees. Both proxy
and API count actual bytes. Only new upload-control JSON gets the 16 KiB limit; legacy
multipart gets the existing file maximum plus 64 KiB envelope allowance. Required file
signatures and recognized MIME/extension conflicts are checked. This does not claim
full format decoding, readability, encryption support or parser page/pixel acceptance.

Public routes expose only exact authorized observations and static errors. They do
not expose staging paths, owner/cleanup tokens, captured credential identifiers,
hidden duplicate counts, raw failures or current/native processing claims. Exact
reuse checks the selected original and live document ACL; revoked choices never
implicitly select another document or create a replacement.
