# Security policy

The latest release (1.x) and the main branch receive security fixes. Older releases are not patched; update to the latest release.

Report vulnerabilities privately through [GitHub private vulnerability reporting](https://github.com/SenjuWoo/Minecraft-Forge/security/advisories/new). Include a minimal reproducer, affected commit, platform and impact. Do not post credentials, private launcher files or a working exploit against another person's system in a public issue.

The CLI reads untrusted mod archives without executing them. Generated Gradle projects execute build code and resolve external dependencies; inspect projects and dependency provenance before running them. Template/wrapper checksums establish byte identity, not a sandbox. Keep launcher worlds and accounts outside development workspaces.
