# Unreal Engine MCP Bridge - Design Document

## Purpose
Enable DIs to interact with Unreal Engine 5.7-5.8 for Hospital Ship Vega development:
- Level design and worldbuilding
- Blueprint visual scripting
- Material and asset management
- Cinematic sequence creation
- Real-time scene inspection

## Architecture

### Bridge Server (Python)
- Runs inside UE Editor via `unreal` Python module
- Exposes MCP-compatible JSON-RPC over stdio or WebSocket
- Sandboxed execution with allowlisted operations
- Async command queue for long-running operations

### MCP Tool Schema (Proposed)

```json
{
  "tools": [
    {
      "name": "ue_spawn_actor",
      "description": "Spawn an actor in the current level",
      "parameters": {
        "class_path": "/Game/Blueprints/BP_HospitalBed",
        "transform": {"location": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]},
        "level": "/Game/Levels/Vega_Ward01"
      }
    },
    {
      "name": "ue_set_material",
      "description": "Apply material to actor or component",
      "parameters": {
        "actor_path": "/Game/Levels/Vega_Ward01.BP_HospitalBed_1",
        "material_path": "/Game/Materials/M_CleanWhite",
        "slot_index": 0
      }
    },
    {
      "name": "ue_run_blueprint_function",
      "description": "Execute a blueprint function on an actor",
      "parameters": {
        "actor_path": "/Game/Levels/Vega_Ward01.BP_Patient_3",
        "function_name": "SetCondition",
        "parameters": {"condition": "Recovering", "severity": 2}
      }
    },
    {
      "name": "ue_create_level_sequence",
      "description": "Create cinematic sequence for video book",
      "parameters": {
        "sequence_name": "Vega_Intro_01",
        "shots": [{"camera": "CineCameraActor_1", "duration": 5.0, "track": "Master"}],
        "output_path": "/Game/Cinematics/"
      }
    },
    {
      "name": "ue_inspect_scene",
      "description": "Get current level hierarchy and actor properties",
      "parameters": {
        "level": "/Game/Levels/Vega_Ward01",
        "filter": "BP_Patient*"
      }
    },
    {
      "name": "ue_import_asset",
      "description": "Import FBX/GLTF/Texture into project",
      "parameters": {
        "source_path": "C:/Assets/hospital_bed.fbx",
        "destination_path": "/Game/Assets/Props/",
        "import_settings": {"generate_materials": true}
      }
    }
  ]
}
```

## Security Model
- Allowlist of permitted classes, functions, and paths
- No arbitrary code execution
- Read-only inspection by default
- Write operations require explicit confirmation

## Integration Points
- **Memory Engine**: Store UE scene state as entities/relationships
- **Skills Registry**: `unreal_engine_bridge_planning` + `vega_worldbuilding_integration`
- **DI Loop**: Autonomous UE operations during heartbeat cycles
- **Vega Narrative**: Sync story beats with level sequences

## Next Steps
1. Prototype bridge server in UE 5.7 Python environment
2. Test stdio MCP transport with Evergrowth MCP server
3. Define allowlist for Vega-specific assets
4. Create first test: spawn hospital bed in ward level
5. Build scene serialization for memory integration

## Files
- `ue_bridge/server.py` - Bridge server (to be created)
- `ue_bridge/tools.json` - MCP tool definitions
- `ue_bridge/allowlist.json` - Security allowlist
- `ue_bridge/README.md` - This document