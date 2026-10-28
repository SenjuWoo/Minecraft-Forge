# Changelog

## 0.2.0 WIP — 2026-10-27

- Add opt-in `init --with-tests`: isolated development mod, two GameTests, a working recipe data provider and XML test reporting. Bare scaffolds retain their existing behavior.
- Generate nine example items from one example block; test registration, placement, successful crafting and rejection of unrelated input.
- Add starter verification for actual generated JSON, nonempty passing XML results, final JAR contents and exclusion of development classes/structures.
- Exercise the full datagen → GameTest → build → artifact-inspection path in CI; include and verify the templates in portable packages.
- Preserve custom Java packages containing the MDK's example mod ID; allow 0.x production versions in the development test-mod dependency.
- Handle proven transient Windows sharing locks during final project publication with a bounded retry, retaining no-overwrite and persistent-error behavior.

## 0.1.0 — 2026-10-27

- Public WIP repository preparation: Windows/Linux CI, real NeoForge build check, package proof, contribution/security policies and roadmap. No stable release declared.

- Initial NeoForge 1.21.1 CLI workbench, pinned official ModDevGradle MDK and target lock.
- Read-only ATLauncher/JAR inventory; source search, library discovery, runtime diagnostics and foreground Gradle workflows.
- Focused agent instructions, test/evidence guidance, optional verified local Java provisioning and portable packaging.
- No standing MCP, global settings changes, launcher deployment or public publication.
