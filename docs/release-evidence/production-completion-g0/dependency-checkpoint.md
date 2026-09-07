# Web dependency remediation checkpoint

Date: 2026-09-07. Candidate: `c5208df`. OPS-03/REL-02 remain open for the broader dependency, image and release checks.

The initial lockfile audit reported six affected packages (four high and two low). `npm audit fix --package-lock-only --ignore-scripts` updated the affected dependency families within the existing manifest ranges. No package was added or removed. React, React DOM, Playwright and the application manifests remained byte-identical. Every changed package retains an npm-registry URL and SHA-512 integrity entry.

| Package | Previous resolved version | Patched resolved version |
| --- | --- | --- |
| Vite | 7.3.2 | 7.3.6 |
| PostCSS | 8.5.10 | 8.5.28 |
| Nano ID | 3.3.11 | 3.3.18 |
| Browserslist | 4.28.2 | 4.28.9 |
| Babel core | 7.29.0 | 7.29.7 |
| esbuild | 0.27.7 | 0.28.2 |

The corresponding Babel helpers, platform-specific esbuild packages and browser compatibility data also advanced. The exact dependency graph and integrity values are retained in [package-lock.json](../../../package-lock.json).

The Vite maintainer documents a Windows development-server file-denial bypass and a patched 7.3.5 release; the selected 7.3.6 is later in that supported major. [Vite advisory](https://github.com/vitejs/vite/security/advisories/GHSA-fx2h-pf6j-xcff). PostCSS's maintainer describes the source-map file-read gap and its 8.5.23 fix; 8.5.28 includes that later correction. [PostCSS advisory](https://github.com/postcss/postcss/security/advisories/GHSA-fxqj-rqcc-2cmp).

Repository inspection shows these build tools are used in the web image's build stage. The final image copies `dist` and `server.mjs`, without the build-stage `node_modules`. This limits their exposure in that image, but does not replace patching development/CI dependencies or prove the complete production image is secure. The Docker base-image tags and broader image assurance remain separate work.

On Oxcart, a clean detached `c5208df` worktree installed the lockfile in the pinned Linux Playwright image, and **npm audit reported zero known vulnerabilities**. Web lint/build and all **70 browser tests passed**, with eight deliberately gated live-stack tests skipped. This run compared the accepted Linux screenshots normally; it did not ignore or regenerate snapshots. Protected evidence is `browser-c5208df.log`, `browser-c5208df/npm-audit.json` and `browser-c5208df/browser-results/` under the owned validation root. A later review-guard candidate `2500c42` also passed **81 browser tests**, web lint/build and the full SAST gate against this lockfile.

These are dated registry-audit and application-regression results, not a guarantee against unknown advisories or a closure of Python dependencies, container scanning, TLS/cookie behavior or production deployment gates.
