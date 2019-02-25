startup_orchestrate:
  runner.state.orchestrate:
    - args:
      - mods: orchestration.startup
      - pillar:
          event_tag: {{ tag }}
          event_data: {{ data }}