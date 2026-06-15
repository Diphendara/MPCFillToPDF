# splash-screen-launcher Specification

## Purpose
Defines the behavior of the application's splash screen launcher.

## Requirements

### Requirement: Splash screen launcher presentation
When the GUI starts, a splash screen window SHALL be displayed. This window SHALL contain:
1. An image placeholder/logo.
2. A button labeled "MPCFill".
3. A button labeled "Web Load".

#### Scenario: App launch displays splash screen
- **WHEN** the user launches the application GUI
- **THEN** the splash screen window is displayed with the logo and the two buttons.

### Requirement: Launch MPCFill window
When the user clicks the "MPCFill" button, the splash screen window SHALL be destroyed/hidden, and the original MPCFill workspace window SHALL open.

#### Scenario: User clicks MPCFill
- **WHEN** the user clicks the "MPCFill" button on the splash screen
- **THEN** the splash screen is closed and the MPCFill window is opened.

### Requirement: Launch Web Load window
When the user clicks the "Web Load" button, the splash screen window SHALL be destroyed/hidden, and the new Web Load workspace window SHALL open.

#### Scenario: User clicks Web Load
- **WHEN** the user clicks the "Web Load" button on the splash screen
- **THEN** the splash screen is closed and the Web Load window is opened.

### Requirement: Main window close behaviour
When either the MPCFill workspace window or the Web Load workspace window is closed by the user, the entire application process SHALL terminate.

#### Scenario: Close workspace window exits application
- **WHEN** the user closes either the MPCFill window or the Web Load window
- **THEN** the entire application exits.
