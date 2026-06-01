import traceback
try:
    from codegenome.tui import main
    main()
except Exception as e:
    print(f"Exception in TUI: {e}")
    traceback.print_exc()
