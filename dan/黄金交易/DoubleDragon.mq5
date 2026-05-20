//+------------------------------------------------------------------+
//|                                     DoubleDragon_Final_Fix.mq5   |
//|                                核心任务：突破200/OCO/3min/追踪/加仓      |
//|                             修复：解决实盘/模拟盘价格精度拒绝问题          |
//+------------------------------------------------------------------+
#property copyright "Expert"
#property strict

#include <Trade\Trade.mqh>

//--- 输入参数
input double LotSize         = 0.1;       // 首单手数
input double AddLotSize      = 0.1;       // 盈利加仓手数
input int    DistancePoints  = 200;       // 挂单距离 (2.0美元)
input int    InitialStopLoss = 10;        // 初始止损 (10点 = 0.1美元)
input int    TrailingStart   = 5;         // 获利 5 点激活追踪与加仓
input int    TrailingStop    = 2;         // 追踪回撤 2 点
input int    TimeLimitMin    = 3;         // 3分钟强平
input double DailyMaxLoss    = 300.0;     // 日损 300 自动关机
input int    MagicNumber     = 888888;

//--- 全局变量
CTrade trade;
datetime DayStartTime;
double   InitialBalance;
bool     IsScaledIn = false;

//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(10);

    // 初始化当日数据
    DayStartTime = iTime(_Symbol, PERIOD_D1, 0);
    InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);

    Print("EA 已加载。当前品种小数位: ", _Digits);
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnTick()
{
    // 1. 核心任务4：日损检查 (防止 InitialBalance 计算错误导致误关机)
    if(InitialBalance <= 0) InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);

    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    if((InitialBalance - currentEquity) >= DailyMaxLoss && DailyMaxLoss > 0)
    {
        Print("🛑 达到日损限制，执行清理并关机。");
        CloseAll();
        ExpertRemove();
        return;
    }

    // 2. 核心管理：追踪、加仓、时间止损
    ManagePositions();

    // 3. 核心任务1 & 2：挂单与 OCO
    ManageOrders();
}

//+------------------------------------------------------------------+
void ManagePositions()
{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    int posCount = 0;

    // 遍历持仓
    for(int i=PositionsTotal()-1; i>=0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionSelectByTicket(ticket) && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
        {
            posCount++;
            double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            double currentSL = PositionGetDouble(POSITION_SL);
            long type = PositionGetInteger(POSITION_TYPE);

            // A. 3分钟时间强平
            if(TimeCurrent() - PositionGetInteger(POSITION_TIME) >= TimeLimitMin * 60)
            {
                trade.PositionClose(ticket);
                continue;
            }

            // B. 获利加仓与追踪
            double points = (type == POSITION_TYPE_BUY) ? (bid - openPrice) : (openPrice - ask);
            points /= _Point;

            if(points >= TrailingStart)
            {
                // 如果当前只有1单且本轮没加过，执行加仓
                if(posCount == 1 && !IsScaledIn)
                {
                    if(type == POSITION_TYPE_BUY)
                        trade.Buy(AddLotSize, _Symbol, NormalizePrice(ask), NormalizePrice(bid - InitialStopLoss*_Point), 0, "ScaleIn");
                    else
                        trade.Sell(AddLotSize, _Symbol, NormalizePrice(bid), NormalizePrice(ask + InitialStopLoss*_Point), 0, "ScaleIn");
                    IsScaledIn = true;
                }

                // 执行追踪止损
                double newSL = (type == POSITION_TYPE_BUY) ? (bid - TrailingStop*_Point) : (ask + TrailingStop*_Point);
                newSL = NormalizePrice(newSL);

                if(type == POSITION_TYPE_BUY && (newSL > currentSL + _Point || currentSL == 0))
                    trade.PositionModify(ticket, newSL, 0);
                else if(type == POSITION_TYPE_SELL && (newSL < currentSL - _Point || currentSL == 0))
                    trade.PositionModify(ticket, newSL, 0);
            }
        }
    }
    if(posCount == 0) IsScaledIn = false;
}

//+------------------------------------------------------------------+
void ManageOrders()
{
    int orders = 0, positions = 0;
    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)) && PositionGetInteger(POSITION_MAGIC) == MagicNumber) positions++;
    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderSelect(OrderGetTicket(i)) && OrderGetInteger(ORDER_MAGIC) == MagicNumber) orders++;

    // OCO: 有持仓则删挂单
    if(positions > 0) { if(orders > 0) CancelOrders(); return; }

    // 挂单
    if(positions == 0 && orders == 0)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

        double pBuy = NormalizePrice(ask + DistancePoints * _Point);
        double pSell = NormalizePrice(bid - DistancePoints * _Point);

        trade.BuyStop(LotSize, pBuy, _Symbol, NormalizePrice(pBuy - InitialStopLoss*_Point), 0);
        trade.SellStop(LotSize, pSell, _Symbol, NormalizePrice(pSell + InitialStopLoss*_Point), 0);
    }
}

//--- 价格规范化核心函数 (解决三位小数报错的关键)
double NormalizePrice(double p)
{
    double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    if(tickSize > 0)
        return(NormalizeDouble(MathRound(p/tickSize)*tickSize, _Digits));
    return(NormalizeDouble(p, _Digits));
}

void CancelOrders()
{
    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderSelect(OrderGetTicket(i)) && OrderGetInteger(ORDER_MAGIC) == MagicNumber)
            trade.OrderDelete(OrderGetTicket(i));
}

void CloseAll()
{
    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)) && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            trade.PositionClose(PositionGetTicket(i));
    CancelOrders();
}