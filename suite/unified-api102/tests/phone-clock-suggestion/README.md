Run from the repository root:

```sh
python3 suite/unified-api102/tests/phone-clock-suggestion/run_tests.py
```

Requires Python 3 and JDK 17 or newer. Uses the existing `deps/api.jar`; set
`ANDROID_JAR` if the installed Android compile jar is elsewhere. Temporary
fixtures/classes stay inside this test directory and are removed after the run.
The logical workspace path is preserved because `suite` may be a symlink.

The runner compares every migrated SHA256 literal with its legacy source, compiles
the three production hooks against the real API102 and Android jars, then runs host
regressions with the real API102 interfaces. Compile-only uses the supplied shared
`Reflect.java` when present, otherwise the test helper's matching contract. Runtime
tests use test-only Android/OEM fixtures and an injectable reflection/hash helper.
No libxposed replacement or legacy API shim is used.

Coverage includes all nine package branches, exact ROM/hash rejection, every
registered interceptor's original exception identity, and at most one original
invocation per call. It exercises:

- SecurityCenter package/metadata flags, hash cache changes, and defensive copies.
- YellowPage request-only CN region, nested restoration, thread isolation,
  antispam-only feature flags, and empty-category import with a reentry guard.
- AudioMonitor callsite/argument/property gates and exception-safe nested cleanup.
- Recorder destination resolution and existing preference restoration.
- MMS process-local fields, OEM OTP consent checks, and null-only partner repair.
- All six Clock allowlist callsites, nearest-caller negative controls, and holiday
  row restoration without exposing other rows in a hidden category.
- Calendar SEARCH action/package/component/resolution gates, copied Intent and
  arguments, retained payload, and exception identity after argument replacement.
- AICR lite/device-tier/RAM gates and optional reflection failures.
- Bounded INFO log payloads and logger failures preserving results/exceptions.

The MMS legacy hook queried the original getter twice for cold partner lookups.
The migration instead proceeds once, and only for a null `recognition_partner_url`
result calls OEM `initMmsConfigJson`, then reads JSONObject field `e` using the same
`has`/`get` behavior as that exact APK's getter. The field name comes from the local
`phone/mms-jadx/sources/com/miui/smsextra/understand/UnderstandFactory.java`:
JADX labels `f10165e` as runtime field `e`. This keeps initialization null/key-scoped
without a second original invocation. Reflection/initializer failure returns the
original null.

Limits: host fixtures do not establish ART interception, actual APK class layout,
framework lifecycle timing, OEM JSON/database behavior, UI behavior, consent flow,
real SMS/recording/calendar behavior, or restart persistence. ROM/APK rejection is
tested with injected hashes; actual APK digests are not recomputed by this harness.
These three legacy files contain no separate framework-file hash guard. Main's
dispatch/API/framework policy remains external to these helpers. No APK is built
or installed, and no device operation is performed.
