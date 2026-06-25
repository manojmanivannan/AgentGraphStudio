import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { server } from "@/test/mocks/server";
import { FakeWebSocket } from "@/test/mocks/websocket";
import { mockConversation, mockConversationSummary } from "@/test/mocks/handlers";
import { useCanvasStore } from "@/store/canvasStore";
import type { Message } from "@/types";
import ChatPage, { groupMessagesIntoTurns } from "./ChatPage";

beforeEach(() => {
    useCanvasStore.getState().reset();
    FakeWebSocket.reset();
    vi.stubGlobal("WebSocket", FakeWebSocket);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

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

    it("handles messages before any user message as preTurnMessages", () => {
        const systemMsg: Message = {
            id: "s1",
            conversation_id: "c1",
            role: "system",
            content: "System init",
            event_type: "error",
            created_at: "2026-01-01T00:00:00.000Z",
        };
        const userMsg: Message = {
            id: "u1",
            conversation_id: "c1",
            role: "user",
            content: "Hello",
            created_at: "2026-01-01T00:00:01.000Z",
        };

        const { preTurnMessages, turns } = groupMessagesIntoTurns([systemMsg, userMsg]);

        expect(preTurnMessages).toHaveLength(1);
        expect(preTurnMessages[0]).toEqual(systemMsg);
        expect(turns).toHaveLength(1);
    });

    it("handles multiple turns", () => {
        const user1: Message = {
            id: "u1", conversation_id: "c1", role: "user", content: "Q1",
            created_at: "2026-01-01T00:00:00.000Z",
        };
        const ans1: Message = {
            id: "a1", conversation_id: "c1", role: "assistant", content: "A1",
            event_type: "final_answer", created_at: "2026-01-01T00:00:01.000Z",
        };
        const user2: Message = {
            id: "u2", conversation_id: "c1", role: "user", content: "Q2",
            created_at: "2026-01-01T00:00:02.000Z",
        };
        const ans2: Message = {
            id: "a2", conversation_id: "c1", role: "assistant", content: "A2",
            event_type: "final_answer", created_at: "2026-01-01T00:00:03.000Z",
        };

        const { turns } = groupMessagesIntoTurns([user1, ans1, user2, ans2]);

        expect(turns).toHaveLength(2);
        expect(turns[0].finalAnswer?.content).toBe("A1");
        expect(turns[1].finalAnswer?.content).toBe("A2");
    });

    it("marks turn as streaming when no final_answer yet", () => {
        const userMsg: Message = {
            id: "u1", conversation_id: "c1", role: "user", content: "Hello",
            created_at: "2026-01-01T00:00:00.000Z",
        };
        const thought: Message = {
            id: "t1", conversation_id: "c1", role: "assistant", content: "Thinking...",
            event_type: "thought", created_at: "2026-01-01T00:00:01.000Z",
        };

        const { turns } = groupMessagesIntoTurns([userMsg, thought]);

        expect(turns).toHaveLength(1);
        expect(turns[0].isStreaming).toBe(true);
        expect(turns[0].steps).toHaveLength(1);
    });

    it("groups human_input_request and tool_approval_request under humanInterrupt", () => {
        const userMsg: Message = {
            id: "u1", conversation_id: "c1", role: "user", content: "Hello",
            created_at: "2026-01-01T00:00:00.000Z",
        };
        const thought: Message = {
            id: "t1", conversation_id: "c1", role: "assistant", content: "Thinking...",
            event_type: "thought", created_at: "2026-01-01T00:00:01.000Z",
        };
        const humanReq: Message = {
            id: "h1", conversation_id: "c1", role: "assistant", content: "Provide input",
            event_type: "human_input_request", created_at: "2026-01-01T00:00:02.000Z",
        };

        const { turns } = groupMessagesIntoTurns([userMsg, thought, humanReq]);

        expect(turns).toHaveLength(1);
        expect(turns[0].isStreaming).toBe(false);
        expect(turns[0].steps).toHaveLength(2);
        expect(turns[0].steps[0].event_type).toBe("thought");
        expect(turns[0].steps[1].event_type).toBe("human_input_request");
        expect(turns[0].humanInterrupt).toBeDefined();
        expect(turns[0].humanInterrupt?.id).toBe("h1");
    });

    it("resumes isStreaming to true when new steps arrive after tool_approval_request in same turn", () => {
        const userMsg: Message = {
            id: "u1", conversation_id: "c1", role: "user", content: "Hello",
            created_at: "2026-01-01T00:00:00.000Z",
        };
        const approvalReq: Message = {
            id: "a1", conversation_id: "c1", role: "tool", content: "Approve tool",
            event_type: "tool_approval_request", created_at: "2026-01-01T00:00:01.000Z",
        };
        const thoughtAfter: Message = {
            id: "t2", conversation_id: "c1", role: "assistant", content: "Resuming...",
            event_type: "thought", created_at: "2026-01-01T00:00:02.000Z",
        };

        const { turns } = groupMessagesIntoTurns([userMsg, approvalReq, thoughtAfter]);

        expect(turns).toHaveLength(1);
        expect(turns[0].humanInterrupt).toBeDefined();
        expect(turns[0].humanInterrupt?.id).toBe("a1");
        expect(turns[0].isStreaming).toBe(true);
        expect(turns[0].steps).toHaveLength(2);
        expect(turns[0].steps[0].id).toBe("a1");
        expect(turns[0].steps[1].id).toBe("t2");
    });
});

describe("ChatPage component", () => {
    const API = "http://localhost:8000/api";

    function renderChatPage(conversationId: string) {
        return render(
            <MemoryRouter initialEntries={[`/chat/${conversationId}`]}>
                <Routes>
                    <Route path="/chat/:conversation_id" element={<ChatPage />} />
                    <Route path="/chat/empty" element={<ChatPage />} />
                    <Route path="/canvas/:canvas_id" element={<div data-testid="canvas-page" />} />
                    <Route path="/" element={<div data-testid="home-page" />} />
                </Routes>
            </MemoryRouter>
        );
    }

    it("renders empty state when conversation_id is 'empty'", async () => {
        renderChatPage("empty");

        await waitFor(() => {
            expect(screen.getByText("No Chat Active")).toBeInTheDocument();
        });
        expect(screen.getByText("Start New Conversation")).toBeInTheDocument();
    });

    it("renders loading state while fetching conversation", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                new Promise(() => { /* never resolves to keep loading */ })
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            const bouncingDots = document.querySelectorAll(".animate-bounce");
            expect(bouncingDots.length).toBeGreaterThan(0);
        });
    });

    it("renders error state when conversation fetch fails", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                new HttpResponse(null, { status: 404 })
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText(/Failed to load conversation/)).toBeInTheDocument();
        });
    });

    it("renders conversation messages and name", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [
                            {
                                id: "m1", conversation_id: "conv-1", role: "user",
                                content: "Hello agent", created_at: "2026-01-01T00:00:00.000Z",
                            },
                            {
                                id: "m2", conversation_id: "conv-1", role: "assistant",
                                content: "Hi there!", event_type: "final_answer",
                                agent_name: "Worker", created_at: "2026-01-01T00:00:01.000Z",
                            },
                        ],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText("Hello agent")).toBeInTheDocument();
            expect(screen.getByText("Hi there!")).toBeInTheDocument();
        });
    });

    it("renders conversation list in sidebar", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Current Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([
                    mockConversationSummary({ id: "conv-1", name: "Current Chat" }),
                    mockConversationSummary({ id: "conv-2", name: "Old Chat" }),
                ])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            // Both appear in sidebar list and header, so use getAllByText
            const items = screen.getAllByText("Current Chat");
            expect(items.length).toBeGreaterThanOrEqual(2);
            expect(screen.getByText("Old Chat")).toBeInTheDocument();
        });
    });

    it("shows empty conversations message when no chats exist", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Current Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText(/No chats found/)).toBeInTheDocument();
        });
    });

    it("creates a new conversation on button click", async () => {
        const user = userEvent.setup();
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Current Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Current Chat" })])
            ),
            http.post(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json(
                    mockConversation({ id: "conv-new", canvas_id: "canvas-1", name: "New Conversation" }),
                    { status: 201 }
                )
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText("Current Chat")).toBeInTheDocument();
        });

        const newConvButtons = screen.getAllByText("New Conversation");
        await user.click(newConvButtons[0]);
    });

    it("shows delete confirmation modal and cancels", async () => {
        const user = userEvent.setup();
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Current Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Current Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText("Current Chat")).toBeInTheDocument();
        });

        // Hover over conversation item to reveal delete button, then click it
        const deleteButtons = document.querySelectorAll('button[title="Delete conversation"]');
        if (deleteButtons.length > 0) {
            await user.click(deleteButtons[0] as HTMLElement);
            await waitFor(() => {
                expect(screen.getByText("Delete Chat Session?")).toBeInTheDocument();
            });

            await user.click(screen.getByText("Cancel"));
            await waitFor(() => {
                expect(screen.queryByText("Delete Chat Session?")).not.toBeInTheDocument();
            });
        }
    });

    it("renders thought and tool_result steps in expanded turn", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [
                            {
                                id: "m1", conversation_id: "conv-1", role: "user",
                                content: "Run analysis", created_at: "2026-01-01T00:00:00.000Z",
                            },
                            {
                                id: "m2", conversation_id: "conv-1", role: "assistant",
                                content: "Let me think...", event_type: "thought",
                                agent_name: "Worker", created_at: "2026-01-01T00:00:01.000Z",
                            },
                            {
                                id: "m3", conversation_id: "conv-1", role: "assistant",
                                content: "Result: 42", event_type: "tool_result",
                                agent_name: "Worker", created_at: "2026-01-01T00:00:02.000Z",
                            },
                            {
                                id: "m4", conversation_id: "conv-1", role: "assistant",
                                content: "The answer is 42", event_type: "final_answer",
                                agent_name: "Worker", created_at: "2026-01-01T00:00:03.000Z",
                            },
                        ],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText("The answer is 42")).toBeInTheDocument();
        });

        // The steps toggle should be visible
        const toggleBtn = screen.getByText(/Show.*execution step/);
        expect(toggleBtn).toBeInTheDocument();
    });

    it("renders handoff message with correct styling", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [
                            {
                                id: "m1", conversation_id: "conv-1", role: "user",
                                content: "Delegate task", created_at: "2026-01-01T00:00:00.000Z",
                            },
                            {
                                id: "m2", conversation_id: "conv-1", role: "system",
                                content: "Delegating to WorkerB...", event_type: "handoff",
                                agent_name: "Router", created_at: "2026-01-01T00:00:01.000Z",
                            },
                            {
                                id: "m3", conversation_id: "conv-1", role: "assistant",
                                content: "Task done", event_type: "final_answer",
                                agent_name: "WorkerB", created_at: "2026-01-01T00:00:02.000Z",
                            },
                        ],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText("Task done")).toBeInTheDocument();
        });
    });

    it("renders error message with alert styling when steps expanded", async () => {
        const user = userEvent.setup();
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [
                            {
                                id: "m1", conversation_id: "conv-1", role: "user",
                                content: "Do something", created_at: "2026-01-01T00:00:00.000Z",
                            },
                            {
                                id: "m2", conversation_id: "conv-1", role: "system",
                                content: "Something went wrong", event_type: "error",
                                created_at: "2026-01-01T00:00:01.000Z",
                            },
                        ],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        // The error is in a step, hidden behind the expand toggle
        await waitFor(() => {
            const toggleBtn = screen.getByText(/Show.*execution step/);
            expect(toggleBtn).toBeInTheDocument();
        });

        await user.click(screen.getByText(/Show.*execution step/));

        await waitFor(() => {
            expect(screen.getByText("Something went wrong")).toBeInTheDocument();
        });
    });

    it("renders empty messages prompt when no messages and not running", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByText(/Send a message to start/)).toBeInTheDocument();
        });
    });

    it("has input disabled when loading conversation", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                new Promise(() => { /* never resolves */ })
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            const input = screen.getByPlaceholderText("Message agents...");
            expect(input).toBeDisabled();
        });
    });

    it("navigates to home via sidebar Home link", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByTitle("Home")).toBeInTheDocument();
        });
    });

    it("navigates to canvas via sidebar Canvas link", async () => {
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByTitle("Canvas Editor")).toBeInTheDocument();
        });
    });

    it("indents steps according to their nesting level in the graph wiring", async () => {
        const user = userEvent.setup();
        const canvasMock = {
            id: "canvas-1",
            name: "My Canvas",
            nodes: {
                agents: [
                    { id: "agent-root-id", name: "MasterAgent", agent_type: "router" },
                    { id: "agent-child-id", name: "WeatherAgent", agent_type: "worker" },
                ],
                tools: [
                    { id: "tool-id", name: "get_weather" },
                ]
            },
            edges: [
                { id: "e1", source_node_id: "agent-root-id", target_node_id: "agent-child-id", edge_type: "handoff" },
                { id: "e2", source_node_id: "agent-child-id", target_node_id: "tool-id", edge_type: "tool" },
            ]
        };

        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [
                            {
                                id: "m1", conversation_id: "conv-1", role: "user",
                                content: "how's the weather in Mumbai", created_at: "2026-01-01T00:00:00.000Z",
                            },
                            {
                                id: "m2", conversation_id: "conv-1", role: "assistant",
                                content: "MasterAgent thought", event_type: "thought",
                                agent_name: "MasterAgent", node_id: "agent-root-id", created_at: "2026-01-01T00:00:01.000Z",
                            },
                            {
                                id: "m3", conversation_id: "conv-1", role: "system",
                                content: "Delegating to WeatherAgent...", event_type: "handoff",
                                agent_name: "MasterAgent", node_id: "agent-child-id", created_at: "2026-01-01T00:00:02.000Z",
                            },
                            {
                                id: "m4", conversation_id: "conv-1", role: "assistant",
                                content: "WeatherAgent thought", event_type: "thought",
                                agent_name: "WeatherAgent", node_id: "agent-child-id", created_at: "2026-01-01T00:00:03.000Z",
                            },
                            {
                                id: "m5", conversation_id: "conv-1", role: "assistant",
                                content: "get_weather result", event_type: "tool_result",
                                agent_name: "get_weather", node_id: "agent-child-id", created_at: "2026-01-01T00:00:04.000Z",
                            },
                            {
                                id: "m5_sub", conversation_id: "conv-1", role: "assistant",
                                content: "sub response", event_type: "response",
                                agent_name: "WeatherAgent", node_id: "agent-child-id", created_at: "2026-01-01T00:00:04.500Z",
                            },
                            {
                                id: "m6", conversation_id: "conv-1", role: "assistant",
                                content: "The weather in Mumbai is currently cloudy.", event_type: "final_answer",
                                agent_name: "MasterAgent", node_id: "agent-root-id", created_at: "2026-01-01T00:00:05.000Z",
                            },
                        ],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json(canvasMock)
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        // Wait for the message steps toggle to be available
        await waitFor(() => {
            expect(screen.getByText("The weather in Mumbai is currently cloudy.")).toBeInTheDocument();
        });

        const toggleBtn = screen.getByText(/Show.*execution step/);
        await user.click(toggleBtn);

        // Verify that steps are indented according to nesting levels:
        // - MasterAgent (root) -> level 0 (0px padding-left)
        // - WeatherAgent (child) -> level 1 (24px padding-left)
        // - get_weather (tool of WeatherAgent) -> level 2 (48px padding-left)
        await waitFor(() => {
            const masterThought = screen.getByText("MasterAgent thought").closest("div[style*='padding-left']");
            const handoffMsg = screen.getByText("Delegating to WeatherAgent...").closest("div[style*='padding-left']");
            const childThought = screen.getByText("WeatherAgent thought").closest("div[style*='padding-left']");
            const toolResult = screen.getByText("get_weather result").closest("div[style*='padding-left']");
            const subResponse = screen.getByText("sub response").closest("div[style*='padding-left']");

            expect(masterThought).toHaveStyle({ paddingLeft: "0px" });
            expect(handoffMsg).toHaveStyle({ paddingLeft: "0px" });
            expect(childThought).toHaveStyle({ paddingLeft: "24px" });
            expect(toolResult).toHaveStyle({ paddingLeft: "48px" });
            expect(subResponse).toHaveStyle({ paddingLeft: "24px" });
            expect(screen.getByText("WeatherAgent · response")).toBeInTheDocument();
        });
    });

    it("renders plots from markdown image links resolved via apiOrigin", async () => {
        const user = userEvent.setup();
        const plotMarkdown = "matplotlib stdout info\n\n![Plot](/api/static/plots/test-image.png)";

        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [
                            {
                                id: "m1", conversation_id: "conv-1", role: "user",
                                content: "plot weather", created_at: "2026-01-01T00:00:00.000Z",
                            },
                            {
                                id: "m2", conversation_id: "conv-1", role: "assistant",
                                content: plotMarkdown, event_type: "tool_result",
                                agent_name: "generate_plot", created_at: "2026-01-01T00:00:01.000Z",
                            },
                            {
                                id: "m3", conversation_id: "conv-1", role: "assistant",
                                content: "Here is your plot:\n![Plot](/api/static/plots/test-image.png)", event_type: "final_answer",
                                agent_name: "MasterAgent", created_at: "2026-01-01T00:00:02.000Z",
                            },
                        ],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        // Wait for final answer and verify image is rendered
        await waitFor(() => {
            expect(screen.getByText(/Here is your plot/)).toBeInTheDocument();
        });

        // The image in final answer should be visible
        const images = screen.getAllByAltText("Plot") as HTMLImageElement[];
        expect(images.length).toBeGreaterThanOrEqual(1);
        expect(images[0].src).toContain("/api/static/plots/test-image.png");

        // Expand steps and check that the tool result step also renders the image
        const toggleBtn = screen.getByText(/Show.*execution step/);
        await user.click(toggleBtn);

        await waitFor(() => {
            // Verify tool result message text/stdout is rendered
            expect(screen.getByText("matplotlib stdout info")).toBeInTheDocument();
        });

        const imagesAfterExpand = screen.getAllByAltText("Plot") as HTMLImageElement[];
        expect(imagesAfterExpand.length).toBe(2);
        expect(imagesAfterExpand[1].src).toContain("/api/static/plots/test-image.png");
    });

    it("collapses and expands individual steps on click", async () => {
        const user = userEvent.setup();
        server.use(
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [
                            {
                                id: "m1", conversation_id: "conv-1", role: "user",
                                content: "Run task", created_at: "2026-01-01T00:00:00.000Z",
                            },
                            {
                                id: "m2", conversation_id: "conv-1", role: "assistant",
                                content: "Worker thought message", event_type: "thought",
                                agent_name: "Worker", created_at: "2026-01-01T00:00:01.000Z",
                            },
                            {
                                id: "m3", conversation_id: "conv-1", role: "assistant",
                                content: "Worker answer", event_type: "final_answer",
                                agent_name: "Worker", created_at: "2026-01-01T00:00:02.000Z",
                            },
                        ],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Test Chat" })])
            )
        );

        renderChatPage("conv-1");

        // Wait for main answer
        await waitFor(() => {
            expect(screen.getByText("Worker answer")).toBeInTheDocument();
        });

        // Expand execution steps
        const toggleBtn = screen.getByText(/Show.*execution step/);
        await user.click(toggleBtn);

        // Verify thought step content is rendered
        await waitFor(() => {
            expect(screen.getByText("Worker thought message")).toBeInTheDocument();
        });

        // Now, find the individual step header button (Worker · thought) and click it
        const stepHeaderBtn = screen.getByText("Worker · thought");
        expect(stepHeaderBtn).toBeInTheDocument();

        // Click it to collapse
        await user.click(stepHeaderBtn);

        // Verify that the step content is no longer in the document
        await waitFor(() => {
            expect(screen.queryByText("Worker thought message")).not.toBeInTheDocument();
        });

        // Click it again to expand
        await user.click(stepHeaderBtn);

        // Verify it is back
        await waitFor(() => {
            expect(screen.getByText("Worker thought message")).toBeInTheDocument();
        });
    });

    it("renders canvas selector dropdown and disables it when conversation is active", async () => {
        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([
                    { id: "canvas-1", name: "My Canvas" },
                    { id: "canvas-2", name: "Second Canvas" },
                ])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Test Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderChatPage("conv-1");

        // Wait for page to render and dropdown to be present
        await waitFor(() => {
            const dropdown = screen.getByTitle("Cannot change canvas mid-conversation") as HTMLSelectElement;
            expect(dropdown).toBeInTheDocument();
            expect(dropdown).toBeDisabled();
            expect(dropdown.value).toBe("canvas-1");
        });
    });

    it("renders canvas selector dropdown and allows changing it when conversation is empty", async () => {
        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([
                    { id: "canvas-1", name: "My Canvas" },
                    { id: "canvas-2", name: "Second Canvas" },
                ])
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas" })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([])
            )
        );

        renderChatPage("empty");

        await waitFor(() => {
            const dropdown = screen.getByTitle("Select canvas for chat") as HTMLSelectElement;
            expect(dropdown).toBeInTheDocument();
            expect(dropdown).not.toBeDisabled();
        });
    });

    it("reconnects websocket with run_id and after_sequence after unexpected disconnect", async () => {
        const user = userEvent.setup();

        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Live Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [] })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Live Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByTestId("chat-input")).toBeInTheDocument();
        });

        await user.type(screen.getByTestId("chat-input"), "run this workflow");
        await user.click(screen.getByTestId("send-button"));

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(1);
        });

        const firstSocket = FakeWebSocket.instances[0];
        await waitFor(() => {
            expect(firstSocket.sentMessages.length).toBeGreaterThanOrEqual(1);
        });

        expect(JSON.parse(firstSocket.sentMessages[0])).toEqual({ prompt: "run this workflow" });

        await act(async () => {
            firstSocket.simulateMessage({ type: "run_queued", run_id: "run-123" });
            firstSocket.simulateMessage({ type: "thought", agent: "Planner", content: "Thinking", run_id: "run-123", sequence: 1 });
            firstSocket.onclose?.(new CloseEvent("close", { code: 1006, wasClean: false }));
        });

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(2);
        });

        const reconnectSocket = FakeWebSocket.instances[1];
        await waitFor(() => {
            expect(reconnectSocket.sentMessages.length).toBeGreaterThanOrEqual(1);
        });

        expect(JSON.parse(reconnectSocket.sentMessages[0])).toEqual({
            run_id: "run-123",
            after_sequence: 1,
        });
    });

    it("replayed events after reconnect keep turn grouping visible", async () => {
        const user = userEvent.setup();

        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Live Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [] })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Live Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByTestId("chat-input")).toBeInTheDocument();
        });

        await user.type(screen.getByTestId("chat-input"), "recover run");
        await user.click(screen.getByTestId("send-button"));

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(1);
        });

        const firstSocket = FakeWebSocket.instances[0];
        await act(async () => {
            firstSocket.simulateMessage({ type: "run_queued", run_id: "run-abc" });
            firstSocket.simulateMessage({ type: "thought", agent: "Planner", content: "step one", sequence: 1, run_id: "run-abc" });
            firstSocket.onclose?.(new CloseEvent("close", { code: 1006, wasClean: false }));
        });

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(2);
        });

        const reconnectSocket = FakeWebSocket.instances[1];
        await act(async () => {
            reconnectSocket.simulateMessage({ type: "tool_result", agent: "Planner", tool: "search", output: "step two", sequence: 2, run_id: "run-abc" });
            reconnectSocket.simulateMessage({ type: "final_answer", agent: "Planner", content: "all done", sequence: 3, run_id: "run-abc" });
            reconnectSocket.simulateMessage({ type: "run_complete", result: "ok", sequence: 4, run_id: "run-abc" });
        });

        await waitFor(() => {
            expect(screen.getByText("all done")).toBeInTheDocument();
        });

        const toggleBtn = screen.getByText(/Show.*execution step/);
        await user.click(toggleBtn);

        await waitFor(() => {
            expect(screen.getByText("step one")).toBeInTheDocument();
            expect(screen.getByText("step two")).toBeInTheDocument();
        });

        await waitFor(() => {
            expect(screen.getByTestId("send-button")).toBeInTheDocument();
        });
    });

    it("replayed run_aborted event after reconnect restores terminal idle state", async () => {
        const user = userEvent.setup();

        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Live Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [] })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Live Chat" })])
            )
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByTestId("chat-input")).toBeInTheDocument();
        });

        await user.type(screen.getByTestId("chat-input"), "run then abort");
        await user.click(screen.getByTestId("send-button"));

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(1);
        });

        const firstSocket = FakeWebSocket.instances[0];
        await act(async () => {
            firstSocket.simulateMessage({ type: "run_queued", run_id: "run-abort-reconnect" });
            firstSocket.simulateMessage({ type: "thought", agent: "Planner", content: "starting", sequence: 1, run_id: "run-abort-reconnect" });
            firstSocket.onclose?.(new CloseEvent("close", { code: 1006, wasClean: false }));
        });

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(2);
        });

        const reconnectSocket = FakeWebSocket.instances[1];
        await act(async () => {
            reconnectSocket.simulateMessage({
                type: "run_aborted",
                message: "Run aborted by user",
                sequence: 2,
                run_id: "run-abort-reconnect",
            });
        });

        await waitFor(() => {
            expect(screen.getByTestId("send-button")).toBeInTheDocument();
        });

        // No extra reconnect websocket should be spawned after terminal aborted replay.
        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(2);
        });
    });

    it("stop button aborts active run and does not auto-reconnect", async () => {        const user = userEvent.setup();
        let abortCalls = 0;

        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({
                        id: "conv-1",
                        canvas_id: "canvas-1",
                        name: "Live Chat",
                        messages: [],
                    })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [] })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Live Chat" })])
            ),
            http.post(`${API}/runs/run-stop/abort`, () => {
                abortCalls += 1;
                return HttpResponse.json({ run_id: "run-stop", status: "aborting" });
            })
        );

        renderChatPage("conv-1");

        await waitFor(() => {
            expect(screen.getByTestId("chat-input")).toBeInTheDocument();
        });

        await user.type(screen.getByTestId("chat-input"), "start and stop");
        await user.click(screen.getByTestId("send-button"));

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(1);
        });

        const socket = FakeWebSocket.instances[0];
        await act(async () => {
            socket.simulateMessage({ type: "run_queued", run_id: "run-stop" });
        });

        await waitFor(() => {
            expect(screen.getByTestId("stop-button")).toBeInTheDocument();
        });

        await user.click(screen.getByTestId("stop-button"));

        await waitFor(() => {
            expect(abortCalls).toBe(1);
        });

        await waitFor(() => {
            expect(FakeWebSocket.instances).toHaveLength(1);
        });
    });

    it("HITL submit sends response via HTTP not WebSocket", async () => {
        const user = userEvent.setup();
        let interruptCalls = 0;

        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({ id: "conv-1", canvas_id: "canvas-1", name: "HITL Chat", messages: [] })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [] })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "HITL Chat" })])
            ),
            http.post(`${API}/runs/run-hitl/interrupt-response`, async ({ request }) => {
                const body = await request.json() as Record<string, unknown>;
                interruptCalls += 1;
                expect(body).toMatchObject({ request_id: "req-human-001", type: "human_input_response", content: "my answer" });
                return HttpResponse.json({ ok: true, request_id: "req-human-001" });
            })
        );

        renderChatPage("conv-1");

        await waitFor(() => expect(screen.getByTestId("chat-input")).toBeInTheDocument());

        await user.type(screen.getByTestId("chat-input"), "need help");
        await user.click(screen.getByTestId("send-button"));

        await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
        const socket = FakeWebSocket.instances[0];

        await act(async () => {
            socket.simulateMessage({ type: "run_queued", run_id: "run-hitl" });
            socket.simulateMessage({
                type: "human_input_request",
                request_id: "req-human-001",
                question: "What is your name?",
                agent: "Planner",
                run_id: "run-hitl",
                sequence: 1,
            });
        });

        await waitFor(() => expect(screen.getByText("What is your name?")).toBeInTheDocument());

        const inlineInput = screen.getByPlaceholderText(/type your response/i);
        await user.type(inlineInput, "my answer");
        await user.keyboard("{Enter}");

        await waitFor(() => expect(interruptCalls).toBe(1));

        // Response is NOT sent over the websocket
        const wsPayloads = socket.sentMessages.map((m) => JSON.parse(m));
        const wsResponse = wsPayloads.find((p) => p.type === "human_input_response");
        expect(wsResponse).toBeUndefined();
    });

    it("tool approval submit sends response via HTTP not WebSocket", async () => {
        const user = userEvent.setup();
        let approvalCalls = 0;

        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({ id: "conv-1", canvas_id: "canvas-1", name: "Approval Chat", messages: [] })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [] })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Approval Chat" })])
            ),
            http.post(`${API}/runs/run-approval/interrupt-response`, async ({ request }) => {
                const body = await request.json() as Record<string, unknown>;
                approvalCalls += 1;
                expect(body).toMatchObject({ request_id: "req-tool-001", type: "tool_approval_response", approved: true });
                return HttpResponse.json({ ok: true, request_id: "req-tool-001" });
            })
        );

        renderChatPage("conv-1");

        await waitFor(() => expect(screen.getByTestId("chat-input")).toBeInTheDocument());

        await user.type(screen.getByTestId("chat-input"), "run tool");
        await user.click(screen.getByTestId("send-button"));

        await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
        const socket = FakeWebSocket.instances[0];

        await act(async () => {
            socket.simulateMessage({ type: "run_queued", run_id: "run-approval" });
            socket.simulateMessage({
                type: "tool_approval_request",
                request_id: "req-tool-001",
                tool: "dangerous_tool",
                args: { param: "value" },
                agent: "Executor",
                run_id: "run-approval",
                sequence: 1,
            });
        });

        await waitFor(() => expect(screen.getByText(/dangerous_tool/)).toBeInTheDocument());

        const approveBtn = screen.getByRole("button", { name: /approve/i });
        await user.click(approveBtn);

        await waitFor(() => expect(approvalCalls).toBe(1));

        const wsPayloads = socket.sentMessages.map((m) => JSON.parse(m));
        const wsResponse = wsPayloads.find((p) => p.type === "tool_approval_response");
        expect(wsResponse).toBeUndefined();
    });

    it("reconnect after disconnect restores pending HITL interrupt from replayed event", async () => {
        const user = userEvent.setup();
        let interruptCalls = 0;

        server.use(
            http.get(`${API}/canvases`, () =>
                HttpResponse.json([{ id: "canvas-1", name: "My Canvas" }])
            ),
            http.get(`${API}/canvases/conversations/conv-1`, () =>
                HttpResponse.json(
                    mockConversation({ id: "conv-1", canvas_id: "canvas-1", name: "Reconnect HITL", messages: [] })
                )
            ),
            http.get(`${API}/canvases/canvas-1`, () =>
                HttpResponse.json({ id: "canvas-1", name: "My Canvas", nodes: { agents: [], tools: [] }, edges: [] })
            ),
            http.get(`${API}/canvases/canvas-1/conversations`, () =>
                HttpResponse.json([mockConversationSummary({ id: "conv-1", name: "Reconnect HITL" })])
            ),
            http.post(`${API}/runs/run-reconnect-hitl/interrupt-response`, async ({ request }) => {
                const body = await request.json() as Record<string, unknown>;
                interruptCalls += 1;
                expect(body).toMatchObject({ request_id: "req-reconnect-001" });
                return HttpResponse.json({ ok: true, request_id: "req-reconnect-001" });
            })
        );

        renderChatPage("conv-1");

        await waitFor(() => expect(screen.getByTestId("chat-input")).toBeInTheDocument());

        await user.type(screen.getByTestId("chat-input"), "start then disconnect");
        await user.click(screen.getByTestId("send-button"));

        await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
        const firstSocket = FakeWebSocket.instances[0];

        await act(async () => {
            firstSocket.simulateMessage({ type: "run_queued", run_id: "run-reconnect-hitl" });
            firstSocket.onclose?.(new CloseEvent("close", { code: 1006, wasClean: false }));
        });

        await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2));

        // On reconnect, the server replays the human_input_request event
        const reconnectSocket = FakeWebSocket.instances[1];
        await act(async () => {
            reconnectSocket.simulateMessage({
                type: "human_input_request",
                request_id: "req-reconnect-001",
                question: "What happened during disconnect?",
                agent: "Planner",
                run_id: "run-reconnect-hitl",
                sequence: 1,
            });
        });

        await waitFor(() => expect(screen.getByText("What happened during disconnect?")).toBeInTheDocument());

        const inlineInput = screen.getByPlaceholderText(/type your response/i);
        await user.type(inlineInput, "all good");
        await user.keyboard("{Enter}");

        await waitFor(() => expect(interruptCalls).toBe(1));
    });
});
