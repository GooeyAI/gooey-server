# Docker & Caprover Deployment

Docker & Caprover files for auxiliary services.

- `Dockerfile` to customize the base service image.
- `captain-definition` file references this Dockerfile so
that Caprover can build the image upon updates

## Usage

In Caprover, at the bottom of Deployment tab, there will be an
option to set the `captain-definition Relative Path`.

Edit this and set it to the correct `*.captain-definition` file.
e.g. for `redis`, set it to `redis.captain-definition`.

Whenever you push changes to the `Dockerfile`, you can hit `Force Build`
in Caprover's deployment tab to rebuild the image. Or, you can configure
Caprover to auto-build on push with its webhooks.
