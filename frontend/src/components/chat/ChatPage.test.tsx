import { describe, expect, it } from "vitest";
import type { Message } from "@/types";
import { groupMessagesIntoTurns } from "./ChatPage";

describe("groupMessagesIntoTurns", () => {
    it("keeps only the last final answer when no handoff occurs", () => {
        const userMsg: Message = {
            id: "u1",
            conversation_id: "c1",
            role: "user",
            content: "Hello",
            created_at: "2026-01-01T00:00:00.000Z",
        };
        const firstFinal: Message = {
            id: "a1",
            conversation_id: "c1",
            role: "assistant",
            content: "First answer",
            agent_name: "Worker",
            event_type: "final_answer",
            created_at: "2026-01-01T00:00:01.000Z",
        };
        const secondFinal: Message = {
            id: "a2",
            conversation_id: "c1",
            role: "assistant",
            content: "Second answer",
            agent_name: "Worker",
            event_type: "final_answer",
            created_at: "2026-01-01T00:00:02.000Z",
        };

        const { turns } = groupMessagesIntoTurns([userMsg, firstFinal, secondFinal]);

        expect(turns).toHaveLength(1);
        expect(turns[0].steps).toHaveLength(0);
        expect(turns[0].finalAnswer).toEqual(secondFinal);
    });

    it("drops intermediate final answers from steps when a handoff occurs", () => {
        const userMsg: Message = {
            id: "u1",
            conversation_id: "c1",
            role: "user",
            content: "Hello",
            created_at: "2026-01-01T00:00:00.000Z",
        };
        const firstFinal: Message = {
            id: "a1",
            conversation_id: "c1",
            role: "assistant",
            content: "Intermediate answer",
            agent_name: "WorkerA",
            event_type: "final_answer",
            created_at: "2026-01-01T00:00:01.000Z",
        };
        const handoffMsg: Message = {
            id: "s1",
            conversation_id: "c1",
            role: "system",
            content: "Delegating to WorkerB...",
            agent_name: "Router",
            event_type: "handoff",
            created_at: "2026-01-01T00:00:01.500Z",
        };
        const secondFinal: Message = {
            id: "a2",
            conversation_id: "c1",
            role: "assistant",
            content: "Final answer",
            agent_name: "WorkerB",
            event_type: "final_answer",
            created_at: "2026-01-01T00:00:02.000Z",
        };

        const { turns } = groupMessagesIntoTurns([userMsg, firstFinal, handoffMsg, secondFinal]);

        expect(turns).toHaveLength(1);
        expect(turns[0].steps).toHaveLength(1);
        expect(turns[0].steps[0]).toEqual(handoffMsg);
        expect(turns[0].finalAnswer).toEqual(secondFinal);
    });
});
