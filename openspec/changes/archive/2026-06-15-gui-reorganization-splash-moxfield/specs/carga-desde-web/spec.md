## REMOVED Requirements

### Requirement: Carga desde web button positioning and trigger
**Reason**: This button is no longer needed on the main MPCFill window as Moxfield deck loading is now handled in a dedicated Web Load workspace window.
**Migration**: Users select the "Web Load" button on the splash screen launcher to open the Web Load workspace.

### Requirement: URL entry dialog interface
**Reason**: The URL input dialog is replaced by a direct input field in the Web Load workspace window.
**Migration**: Enter the Moxfield URL directly in the input field of the Web Load window.

### Requirement: Dialog cancellation
**Reason**: The modal dialog no longer exists.
**Migration**: None.

### Requirement: Dialog acceptance
**Reason**: The modal dialog no longer exists.
**Migration**: Use the "Cargar" button in the Web Load window to fetch the deck.
