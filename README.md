# Autumn

<p align="center">
    <img src="https://i.imgur.com/1bXTXQe.png" alt="Autumn logo" width="120" />
</p>

<p align="center">
    <strong>A modern ASGI web framework focused on typed controllers, dependency injection, and clean configuration.</strong>
</p>

<a href="https://autumn.de4oult.online/en" target="_blank">__Autumn__</a> is a Python web framework for building HTTP APIs and WebSocket applications with a small, explicit core. It leans on Python's type system instead of large decorator stacks: route parameters are typed, request bodies are inferred from Pydantic models, dependencies are injected from signatures, and responses can be serialized automatically.

If you want class-based controllers, typed configuration, built-in dependency injection, OpenAPI/Dependencies docs generation, and CORS support, Autumn is built for that style.

## Highlights
- ASGI-first application object that works with standard ASGI servers such as `uvicorn`
- Class-based REST controllers with typed path parameters like `{id:int}` and `{file:path}`
- Signature-driven dependency injection with `@service` and `@leaf`
- Explicit module discovery without recursive filesystem execution
- Automatic request body validation from Pydantic annotations
- Automatic JSON serialization for Pydantic return values
- Built-in configuration system with environment, JSON, and YAML sources
- Built-in configs for application settings, CORS, and WebSocket tuning
- OpenAPI and dependencies documentation generation with built-in viewer
- Middleware hooks, lifespan hooks, file responses, redirects, and streaming
- WebSocket routes with dependency injection support

## Why Autumn
__Autumn__ tries to keep the ergonomic parts of modern Python frameworks while staying direct:
- Controllers are just Python classes.
- Dependencies come from constructor or method signatures.
- Request bodies are inferred from type annotations instead of extra decorators.
- Configs are plain Python classes with typed fields.
- The framework stays close to raw ASGI concepts when you need to drop lower.

That makes the happy path concise, while still keeping the codebase readable when the application grows.

## Benchmarks
Latest repeated local benchmark run: `2026-08-12`

Environment:
- Windows
- Python `3.12`
- `uvicorn --workers 1 --loop asyncio --http httptools --lifespan off`
- Concurrency: `64`
- Warmup: `2s` per scenario
- Measurement duration: `8s` per scenario
- Repetitions: `5`, randomized framework and scenario order
- Reported values: median of repetitions

Median RPS by scenario:

| Framework | Plaintext | JSON | Path parameter | Validated body |
| --- | ---: | ---: | ---: | ---: |
| Falcon | 8381.56 | 8347.52 | 8391.16 | 6967.47 |
| Starlette | 8403.90 | 8333.73 | 8264.93 | 6748.19 |
| __Autumn__ | 8107.42 | 8223.67 | 7993.92 | 6866.13 |
| FastAPI | 7470.63 | 6787.41 | 5810.57 | 5277.82 |

In this run, Autumn is `23.06%` faster than FastAPI on average, `1.76%` behind
Starlette, and `2.79%` behind Falcon. The comparison contains 80 measurements in
total; every measured request completed successfully.

## Explicit module discovery

Autumn never scans and executes every Python file below the project root. Modules
that contain independently decorated controllers, services, lifecycle hooks, or
configuration are listed explicitly:

```python
app = Autumn(
    discover = (
        'project.controllers',
        'project.services',
    )
)
```

When `root_path` is provided, module names are resolved relative to that directory.
When a discovered name points to a package, Autumn loads every Python module and
nested package inside it. This makes `discover = 'project.controllers'` sufficient
for a controllers package with multiple files. Discovery stays within each explicitly
listed package; imports made by its modules continue to work normally.

## Philosophy

__Autumn__ favors:

- strong typing over implicit magic
- signatures over decorator-heavy ceremony
- built-in primitives over mandatory third-party integration
- readable application structure over framework cleverness

The goal is to make small apps pleasant and larger apps maintainable.

## Author
```
     _      _  _               _ _   
  __| | ___| || |   ___  _   _| | |_ 
 / _` |/ _ \ || |_ / _ \| | | | | __|
| (_| |  __/__   _| (_) | |_| | | |_ 
 \__,_|\___|  |_|  \___/ \__,_|_|\__|
```

## __Thank you a lot!__

<br>

## How to reach me
<a href="https://t.me/kayra_dev">
    <img src="https://img.shields.io/badge/-Telegram-informational?style=for-the-badge&logo=telegram" alt="Telegram Badge" height="30" />
</a>
<img src="https://img.shields.io/badge/-kayra.dist@gmail.com-informational?style=for-the-badge&logo=gmail" alt="Gmail Badge" height="30" />
