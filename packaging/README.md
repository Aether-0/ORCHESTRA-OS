# Native-package tooling

[build-package.sh](build-package.sh) and [stage-payload.sh](stage-payload.sh)
stage native distribution packages; [generate-sbom.sh](generate-sbom.sh)
records package contents. [package-smoke.sh](package-smoke.sh) exercises the
package lifecycle. The separate legacy v1.0.0 package workflow is manual.

The current public release provides source archives and evidence documentation,
not native DEB/RPM/APK assets or hosted package attestations. See the
[current release guide](../docs/releases/v1.0.4-source.md). Kernel artifacts
remain target-specific; installation must not implicitly activate sched_ext.
