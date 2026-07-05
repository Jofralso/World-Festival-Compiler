# FestivalWorld Paper plugin

This plugin provides a local Paper-side entry point for FestivalWorld. It listens for /festivalworld <place> <festival> and can trigger the local export workflow from the server host.

## Build

```bash
mvn package
```

## What it does

- accepts a place and festival name from in-game commands
- emits a deployment request for the local FestivalWorld export pipeline
- is intended to be paired with a host-side wrapper or deployment script
