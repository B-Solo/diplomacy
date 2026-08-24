# Functional Specification

## Diplomacy Context

Diplomacy is a board game in which players move armies and fleets around a map divided into territories.
Unlike Risk, Diplomacy is not turn-based: all players submit orders for a phase, after which those orders are resolved simultaneously.
A basic knowledge of Diplomacy is assumed throughout this document.

## Problem Statement

This application is a supporting tool for running and managing an online game of Diplomacy.
Communication with players takes place outside the application.
The application tracks game state, resolves orders and, most critically, produces graphics through which the gamemaster communicates the game state to players.

The application supports custom maps using the standard Diplomacy rules.
Custom maps may change the geography, powers, supply centres and starting state, but arbitrary rules variants are not an objective.

The application also supports an optional Fog of War mode in which each power is aware only of its immediate surroundings.
Visibility rules are configurable for each game; by default, a power can see territories containing its units and territories adjacent to those units.
Ordinary games use full visibility.

The application is personal-first: it is intended for the gamemaster's own use, but its engine and game data remain sufficiently separate for it to be reused and adapted for future games.
It is not intended for distribution as a general-purpose product.

## High-Level Overview

At its core, the application supports the following operations:

- Display the full game map in its current state.
- Display recorded moves, builds and retreats over the current state to illustrate the submitted orders.
- Repeat these operations for a user-selected subsection of the map, producing diagrams that are easier for players to interpret.
- Repeat the applicable views from the perspective of a selected power in Fog of War games, omitting information that the power cannot see even when it falls within the displayed area.
- Receive, validate and resolve orders, builds and retreats.
- Advance the game and record its next state only when explicitly requested by the gamemaster.

Communicating the game or its orders to players is explicitly out of scope and remains the responsibility of the gamemaster.
The application provides the visual output used for that communication and assists the gamemaster in maintaining and updating the game state.

## Design and Requirements

The application is a local executable rather than a hosted website.
It is intended to be written in Python and use an isolated environment so that it is straightforward to move between computers.
Windows is the primary runtime platform, with portability and testing maintained on macOS.
Application workflows remain within one main window so changing task does not create a stack of secondary application windows.

The application engine and game data are separate.
The gamemaster owns a self-contained game folder containing a structured SVG map whose territory shapes are individually identifiable, structured map definitions describing territory names, types, supply centres and connections, and JSON files describing the game state and orders.
The folder contains every game state and its associated orders, allowing a game to be moved, reopened, reviewed and continued without additional application-owned data.

The application renders the map from the selected game state.
The gamemaster can select an area of the map to enlarge and copy the resulting image to the clipboard.
The gamemaster can overlay orders diagrammatically, including arrows for movements, convoys and supports, and move backwards and forwards through the recorded game history.

A separate order-entry view accepts plain-text orders using either territory abbreviations or full names.
The application retains the submitted text, performs initial validation and records a canonical interpretation for use by the rest of the application.

The existing `diplomacy` Python package is expected to provide the rules and adjudication behavior.
A local copy is shipped with the application so that it can be modified if required.

## Code Structure

Good, modular and tested code is paramount.
The code must be approachable to a developer who is familiar with Python but unfamiliar with this codebase.
This requires docstrings, comments that explain non-obvious logic, sensible modularisation and clear contracts between modules and APIs.
