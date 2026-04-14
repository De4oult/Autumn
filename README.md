# Autumn

<p align="center">
    <img src="https://i.imgur.com/1bXTXQe.png" alt="Autumn logo" width="120" />
</p>

<p align="center">
    <strong>A modern ASGI web framework focused on typed controllers, dependency injection, and clean configuration.</strong>
</p>

__Autumn__ is a Python web framework for building HTTP APIs and WebSocket applications with a small, explicit core. It leans on Python's type system instead of large decorator stacks: route parameters are typed, request bodies are inferred from Pydantic models, dependencies are injected from signatures, and responses can be serialized automatically.

If you want class-based controllers, typed configuration, built-in dependency injection, OpenAPI/Dependencies docs generation, and CORS support, Autumn is built for that style.

## Highlights
- ASGI-first application object that works with standard ASGI servers such as `uvicorn`
- Class-based REST controllers with typed path parameters like `{id:int}` and `{file:path}`
- Signature-driven dependency injection with `@service` and `@leaf`
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
| Framework   | RPS   | Latency (ms) |
| ----------- | ----- | ------------ |
| __Autumn__* | 1970  | 50.25        |
| FastAPI     | 3161  | 31.17        |
| Flask       | 1228  | 2743.86      |

___\* Autumn__ is under active development, and performance will continue to improve as the framework evolves._


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
