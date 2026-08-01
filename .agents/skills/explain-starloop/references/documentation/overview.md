# Starloop overview

Starloop is an installable product and engineering operating system for Codex and Claude Code. It
combines research-first judgment, explicit human gates, autonomous delivery, verification,
technical teaching, optional ChatGPT web images, and an optional multi-session Crew runtime.

Starloop helps the user:

- turn an outcome into a bounded product and engineering decision;
- preserve important decisions without generating empty document suites;
- implement a coherent vertical slice after an explicit go;
- verify real behavior proportionally to risk;
- delegate economical work without losing a strong coordinator;
- recover local work across terminal, account, or provider changes;
- compare direct and Crew execution by time, usage, evidence, and defects.

Starloop does not replace the host agent, Git, tests, provider authentication, human product
judgment, or formal security assessment. Crew is optional. In direct mode the primary session still
uses the normal Starloop loop without starting teammates.

The current Git root is the project boundary. Sessions in subdirectories of one repository share
one Starloop project. Another Git root is isolated. Provider credentials and the optional
ChatGPT-web browser profile are user-scoped; project decisions, Crew state, tasks, metrics, and
independent handoff bundles are project-scoped. Handoff may discover user-scoped provider session
files, but includes only a selected conversation whose recorded working directory belongs to the
current Git root.
