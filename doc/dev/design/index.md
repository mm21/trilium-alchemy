# Design

## Entities

```{uml} entity.plantuml
```

## Entity state machine

The entity state ({obj}`Entity.state`) is automatically managed based on the user's actions.

```{uml} entity-state.plantuml
```

## Flush procedure

The following captures the mechanism to commit changes to Trilium, beginning with {obj}`Session.flush`.

It's recommended to right click and "Open image in new tab".

```{uml} flush.plantuml
```