/**
 * AS - the open source Automotive Software on https://github.com/parai
 *
 * Copyright (C) 2017  AS <parai@foxmail.com>
 *
 * This source code is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2 as published by the
 * Free Software Foundation; See <http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt>.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
 * or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
 * for more details.
 */
#ifdef ENABLE_FIFO_SCHED
/* ============================ [ INCLUDES  ] ====================================================== */
#include "kernel_internal.h"
#include "asdebug.h"
/* ============================ [ MACROS    ] ====================================================== */
#define SCHED_FIFO_SIZE(fifo) ((fifo)->pFIFO)[0]
#define SCHED_FIFO_HEAD(fifo) ((fifo)->pFIFO)[1]
#define SCHED_FIFO_TAIL(fifo) ((fifo)->pFIFO)[2]

#define SCHED_FIFO_SLOT_OFFSET 3
/* ============================ [ TYPES     ] ====================================================== */
/* ============================ [ DECLARES  ] ====================================================== */
/* ============================ [ DATAS     ] ====================================================== */
extern const ReadyFIFOType ReadyFIFO[PRIORITY_NUM+1];
#if (PRIORITY_NUM > 63)
static uint8 ReadyGroup;
#endif

#if (PRIORITY_NUM > 7)
static uint8 ReadyGroupTable[(PRIORITY_NUM+64)/64];
#endif

static uint8 ReadyMapTable[(PRIORITY_NUM+8)/8];
/**************************************************
#include <stdio.h>
int main(int argc, char *argv[])
{
    unsigned int i;
    printf("static uint8_t tableUnMap[256]=\n{");
    for (i=0; i <= 0xff; ++i)
    {
        if(i%16==0) printf("\n\t");
        if(i&(1u<<7))
            printf("7,");
        else if(i&(1u<<6))
            printf("6,");
        else if(i&(1u<<5))
            printf("5,");
        else if(i&(1u<<4))
            printf("4,");
        else if(i&(1u<<3))
            printf("3,");
        else if(i&(1u<<2))
            printf("2,");
        else if(i&(1u<<1))
            printf("1,");
        else if(i&(1u<<0))
            printf("0,");
        else printf("0,");
    }
    printf("\n}\n");
    return 0;
}
used to generate the map like ucos,but inverted from low to high
*******************************************************/
static uint8_t tableUnMap[256]=
{
	0,0,1,1,2,2,2,2,3,3,3,3,3,3,3,3,
	4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,
	5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,
	5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,
	6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
	6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
	6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
	6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
	7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
};
/* ============================ [ LOCALS    ] ====================================================== */
static inline void Sched_SetReadyBit(PriorityType priority)
{
#if (PRIORITY_NUM > 63)
	ReadyGroup |= (1u << (priority >> 6));
#endif

#if (PRIORITY_NUM > 7)
	ReadyGroupTable[priority >> 6] |= (1u << ((priority&0x3Fu) >> 3));
#endif

	ReadyMapTable[(priority >> 6)*8 + ((priority&0x3Fu) >> 3)] |= (1u << ((priority&0x3Fu) & 0x7u));
}

static inline void Sched_ClearReadyBit(PriorityType priority)
{
	ReadyMapTable[(priority >> 6)*8 + ((priority&0x3Fu) >> 3)] &= ~(1u << ((priority&0x3Fu) & 0x7u));

#if (PRIORITY_NUM > 7)
	if(0u == ReadyMapTable[(priority >> 6)*8 + ((priority&0x3Fu) >> 3)])
	{
		ReadyGroupTable[priority >> 6] &= ~(1u << ((priority&0x3Fu) >> 3));
	}
#endif

#if (PRIORITY_NUM > 63)
	if(0u == ReadyGroupTable[priority >> 6])
	{
		ReadyGroup &= ~(1u << (priority >> 6));
	}
#endif
}

static inline PriorityType Sched_GetReadyBit(void)
{
#if (PRIORITY_NUM > 63)
	uint8 Z;
#endif
#if (PRIORITY_NUM > 7)
	uint8 X;
#endif
	uint8 Y;

#if (PRIORITY_NUM > 63)
	Z = tableUnMap[ReadyGroup];
#else
#define Z 0u
#endif

#if (PRIORITY_NUM > 7)
	X = tableUnMap[ReadyGroupTable[Z]];
#else
#define X 0u
#endif

	Y = tableUnMap[ReadyMapTable[(Z<<6) + X]];

	return ((Z<<6) + (X<<3) + Y);
}

static void Sched_AddReadyInternal(TaskType TaskID, PriorityType priority)
{
	const ReadyFIFOType* fifo;

	asAssert(priority <= PRIORITY_NUM);

	fifo = &ReadyFIFO[priority];

	asAssert(fifo->pFIFO);

	asAssert(SCHED_FIFO_SIZE(fifo) < (fifo->max-SCHED_FIFO_SLOT_OFFSET));

	SCHED_FIFO_SIZE(fifo) ++;
	fifo->pFIFO[SCHED_FIFO_TAIL(fifo)] = TaskID;
	SCHED_FIFO_TAIL(fifo) ++;
	if(SCHED_FIFO_TAIL(fifo) >= fifo->max)
	{
		SCHED_FIFO_TAIL(fifo) = SCHED_FIFO_SLOT_OFFSET;
	}

	Sched_SetReadyBit(priority);

	if(ReadyVar == RunningVar)
	{
		priority = Sched_GetReadyBit();
		fifo = &ReadyFIFO[priority];
		asAssert(fifo->pFIFO);
	}

	ReadyVar = &TaskVarArray[fifo->pFIFO[SCHED_FIFO_HEAD(fifo)]];
}
/* ============================ [ FUNCTIONS ] ====================================================== */
void Sched_Init(void)
{
	PriorityType prio;

	for(prio=0; prio <= PRIORITY_NUM; prio++)
	{
		if(ReadyFIFO[prio].pFIFO != NULL)
		{
			SCHED_FIFO_SIZE(&ReadyFIFO[prio]) = 0;
			SCHED_FIFO_HEAD(&ReadyFIFO[prio]) = SCHED_FIFO_SLOT_OFFSET;
			SCHED_FIFO_TAIL(&ReadyFIFO[prio]) = SCHED_FIFO_SLOT_OFFSET;
		}
	}

#if (PRIORITY_NUM > 63)
	ReadyGroup = 0;
#endif

#if (PRIORITY_NUM > 7)
	for(prio=0; prio < sizeof(ReadyGroupTable); prio++)
	{
		ReadyGroupTable[prio] = 0;
	}
#endif

	for(prio=0; prio < sizeof(ReadyMapTable); prio++)
	{
		ReadyMapTable[prio] = 0;
	}
}

void Sched_AddReady(TaskType TaskID)
{
	Sched_AddReadyInternal(TaskID, TaskConstArray[TaskID].initPriority);
}

#if(OS_PTHREAD_NUM > 0)
void Sched_PosixAddReady(TaskType TaskID)
{
	Sched_AddReadyInternal(TaskID, TaskVarArray[TaskID].priority);
}
#endif
void Sched_Preempt(void)
{
	PriorityType priority;
	const ReadyFIFOType* fifo;

	OSPostTaskHook();
	/* remove the ReadyVar from the queue */
	priority = ReadyVar->priority;
	fifo = &ReadyFIFO[priority];
	asAssert(fifo->pFIFO);

	SCHED_FIFO_SIZE(fifo) --;
	if(0u == SCHED_FIFO_SIZE(fifo))
	{
		Sched_ClearReadyBit(priority);
	}

	SCHED_FIFO_HEAD(fifo) ++;
	if(SCHED_FIFO_HEAD(fifo) >= fifo->max)
	{
		SCHED_FIFO_HEAD(fifo) = SCHED_FIFO_SLOT_OFFSET;
	}

	/* put the RunningVar back to the head of queue */
	priority = RunningVar->priority;
	fifo = &ReadyFIFO[priority];
	asAssert(fifo->pFIFO);

	SCHED_FIFO_SIZE(fifo) ++;
	SCHED_FIFO_HEAD(fifo) --;
	if(SCHED_FIFO_HEAD(fifo) < SCHED_FIFO_SLOT_OFFSET)
	{
		SCHED_FIFO_HEAD(fifo) = fifo->max-1;
	}
	fifo->pFIFO[SCHED_FIFO_HEAD(fifo)] = RunningVar - TaskVarArray;

	Sched_SetReadyBit(priority);
}

void Sched_GetReady(void)
{
	const ReadyFIFOType* fifo;

	PriorityType priority = Sched_GetReadyBit();

	fifo = &ReadyFIFO[priority];
	if(NULL != fifo->pFIFO)
	{
		if(SCHED_FIFO_SIZE(fifo) > 0)
		{
			/* remove the ReadyVar from the queue */
			ReadyVar = &TaskVarArray[fifo->pFIFO[SCHED_FIFO_HEAD(fifo)]];
			SCHED_FIFO_SIZE(fifo) --;
			if(0u == SCHED_FIFO_SIZE(fifo))
			{
				Sched_ClearReadyBit(priority);
			}

			SCHED_FIFO_HEAD(fifo) ++;
			if(SCHED_FIFO_HEAD(fifo) >= fifo->max)
			{
				SCHED_FIFO_HEAD(fifo) = SCHED_FIFO_SLOT_OFFSET;
			}
		}
		else
		{
			ReadyVar = NULL;
		}
	}
	else
	{
		ReadyVar = NULL;
	}
}

bool Sched_Schedule(void)
{
	bool needSchedule = FALSE;
	const ReadyFIFOType* fifo;

	PriorityType priority = Sched_GetReadyBit();

	fifo = &ReadyFIFO[priority];
	if(NULL != fifo->pFIFO)
	{
		if(SCHED_FIFO_SIZE(fifo) > 0)
		{
			ReadyVar = &TaskVarArray[fifo->pFIFO[SCHED_FIFO_HEAD(fifo)]];

			if(ReadyVar->priority >  RunningVar->priority)
			{
				/* remove the ReadyVar from the queue */
				SCHED_FIFO_SIZE(fifo) --;
				if(0u == SCHED_FIFO_SIZE(fifo))
				{
					Sched_ClearReadyBit(priority);
				}

				SCHED_FIFO_HEAD(fifo) ++;
				if(SCHED_FIFO_HEAD(fifo) >= fifo->max)
				{
					SCHED_FIFO_HEAD(fifo) = SCHED_FIFO_SLOT_OFFSET;
				}

				/* put the RunningVar back to the head of queue */
				priority = RunningVar->priority;
				fifo = &ReadyFIFO[priority];
				asAssert(fifo->pFIFO);

				SCHED_FIFO_SIZE(fifo) ++;
				SCHED_FIFO_HEAD(fifo) --;
				if(SCHED_FIFO_HEAD(fifo) < SCHED_FIFO_SLOT_OFFSET)
				{
					SCHED_FIFO_HEAD(fifo) = fifo->max-1;
				}
				fifo->pFIFO[SCHED_FIFO_HEAD(fifo)] = RunningVar - TaskVarArray;

				Sched_SetReadyBit(priority);
				needSchedule = TRUE;
			}
		}
	}

	return needSchedule;
}
#endif /* ENABLE_FIFO_SCHED */
