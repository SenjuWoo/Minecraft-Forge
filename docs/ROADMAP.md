# Roadmap and status

## Available in 0.2.0 WIP

- NeoForge1.21.1 project scaffolding from a pinned official ModDevGradle template.
- Foreground Gradle workflow with JDK21 discovery and optional verified local Windows provisioning.
- Read-only ATLauncher/JAR inventory, bounded source search and Modrinth discovery.
- Focused agent guides, offline diagnostics and portable packaging.
- Opt-in `init --with-tests`: separate development test mod, two GameTests, a recipe data provider and a verifier for generated JSON, XML test cases and the final mod JAR.

## Next priorities

- Improve actionable dependency/crash evidence while keeping uncertain diagnoses explicit.
- Expand behavior examples beyond the starter block/recipe slice as concrete mod requests require them.
- Validate client/dedicated-server workflows and fresh Java provisioning on clean machines.
- Add another Minecraft/NeoForge target only with its own template pins and tests.

Fabric and Forge are future providers. MCP integration is conditional on a workflow needing persistent state; there is no always-on server planned. Roadmap items have no promised dates. The project does not claim universal modpack compatibility or automatic crash repair.
