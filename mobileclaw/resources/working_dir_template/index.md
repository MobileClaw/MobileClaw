# Overview

This directory contains all data of the organization.

## Principles

- All data is saved as unstructured markdown files instead of structured databases. The markdown content may contain images or other files, which are stored under the `files` directory grouped by date, and referenced as links in the markdown files.
- The markdown files refer to each other with links, just like Internet webpages linking to each other. Storing data is like creating webpages, and data retrieval is like navigating the web for the information.
- Data generation and retrieval are handled by a large language model (the brain) in an agentic (multi-hop) way.
- Permission: All members can read the whole directory (including the org-shared files); Members with "manager" permission can write the `org_shared/files` and `org_shared/knowledge` directory. A normal member can only write its own directory. All members should not write log.md files since they are maintained automatically.
- The `org_shared/knowledge` contains information that is useful for doing jobs. This can include success/failure experience of executing tasks, internal documents about products/services, interesting news/posts collected when browsering different apps. Each agent also has its own knowledge.

